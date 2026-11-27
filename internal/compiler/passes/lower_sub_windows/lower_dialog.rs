// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! Lowering of a `Dialog` declared within another component, which gets its own window when shown.

use super::{check_no_reference_to_sub_window, detach_root_position};
use crate::builtin_functions::BuiltinFunction;
use crate::diagnostics::{BuildDiagnostics, SourceLocation, Spanned};
use crate::element_type::PropertyLookupMode;
use crate::expression_tree::Expression;
use crate::expression_tree::{BindingExpression, Callable, NamedReference};
use crate::expression_types::Orientation;
use crate::langtype::Type;
use crate::layout::{GridLayout, Layout, LayoutGeometry, create_new_prop};
use crate::native_class::PropertyVisibility;
use crate::object_tree::*;
use crate::typeregister::layout_info_type;
use by_address::ByAddress;
use smol_str::{SmolStr, format_smolstr};
use std::cell::RefCell;
use std::collections::HashSet;
use std::rc::Rc;

/// Whether the element is a `Dialog`, or a component inheriting from `Dialog`
pub fn is_dialog(element: &ElementRc) -> bool {
    element.borrow().builtin_type().is_some_and(|b| b.name == "Dialog")
}

/// The Dialogs that `show()` or `show-modal()` is called on, within the component.
/// Only these get their own window: a Dialog that is never shown lays out its buttons in place.
#[allow(clippy::mutable_key_type)]
pub(super) fn collect_shown_dialogs(component: &Rc<Component>) -> HashSet<ByAddress<ElementRc>> {
    let mut shown = HashSet::new();
    recurse_elem_including_sub_components_no_borrow(component, &(), &mut |elem, _| {
        visit_element_expressions(elem, |exp, _, _| {
            exp.visit_recursive(&mut |e| {
                if let Expression::FunctionCall { function, arguments, .. } = e
                    && matches!(
                        function,
                        crate::expression_tree::Callable::Builtin(
                            BuiltinFunction::ShowDialog | BuiltinFunction::ShowDialogModal
                        )
                    )
                    && let [Expression::ElementReference(dialog), ..] = arguments.as_slice()
                    && let Some(dialog) = dialog.upgrade()
                {
                    shown.insert(ByAddress(dialog));
                }
            });
        });
    });
    shown
}

/// Lower a `Dialog` declared within another component into its own component,
/// which is only instantiated while shown with `show()` or `show-modal()`.
/// Unlike a PopupWindow, the Dialog stays a Dialog, so that its buttons get laid out.
pub(super) fn lower_dialog(
    dialog_element: &ElementRc,
    parent_element: Option<&ElementRc>,
    diag: &mut BuildDiagnostics,
) {
    let parent_component = dialog_element.borrow().enclosing_component.upgrade().unwrap();
    let Some(parent_element) =
        parent_element.filter(|_| !Rc::ptr_eq(&parent_component.root_element, dialog_element))
    else {
        // The root of a repeated or conditional sub-component
        diag.push_error(
            "A Dialog that is shown with show() or show-modal() cannot be directly repeated or conditional".into(),
            &*dialog_element.borrow(),
        );
        return;
    };

    remove_lowered_element(dialog_element, parent_element);
    parent_element.borrow_mut().has_sub_window_child = true;

    let dialog_comp = Rc::new(Component {
        root_element: dialog_element.clone(),
        parent_element: RefCell::new(Rc::downgrade(parent_element)),
        ..Component::default()
    });

    let weak = Rc::downgrade(&dialog_comp);
    recurse_elem(&dialog_comp.root_element, &(), &mut |e, _| {
        e.borrow_mut().enclosing_component = weak.clone()
    });

    let origin = detach_root_position(&dialog_comp, "dialog");

    check_no_reference_to_sub_window(dialog_element, &parent_component, &weak, &origin, diag);
    check_dialog_functions_from_outside(dialog_element, &parent_component, diag);
    check_dialog_not_shown_from_inside(&dialog_comp, diag);

    crate::passes::focus_handling::call_focus_on_init(&dialog_comp);

    parent_component.sub_windows.borrow_mut().push(SubWindow {
        component: dialog_comp,
        parent_element: parent_element.clone(),
        kind: SubWindowKind::Dialog,
    });
}

fn is_dialog_function(f: &crate::expression_tree::Callable) -> bool {
    matches!(
        f,
        crate::expression_tree::Callable::Builtin(
            BuiltinFunction::ShowDialog
                | BuiltinFunction::ShowDialogModal
                | BuiltinFunction::HideDialog
        )
    )
}

/// The enclosing component can only call `show()`, `show-modal()` and `hide()` on a Dialog it declares,
/// because the Dialog only exists while it's shown.
fn check_dialog_functions_from_outside(
    dialog_element: &ElementRc,
    parent_component: &Rc<Component>,
    diag: &mut BuildDiagnostics,
) {
    fn check(
        expr: &Expression,
        dialog_element: &ElementRc,
        span: &SourceLocation,
        diag: &mut BuildDiagnostics,
    ) {
        let is_dialog =
            |e: &ElementWeak| e.upgrade().is_some_and(|e| Rc::ptr_eq(&e, dialog_element));
        match expr {
            Expression::FunctionCall { function, arguments, .. }
                if is_dialog_function(function)
                    && matches!(arguments.as_slice(), [Expression::ElementReference(e), ..] if is_dialog(e)) =>
            {
                arguments[1..].iter().for_each(|a| check(a, dialog_element, span, diag))
            }
            Expression::ElementReference(e) if is_dialog(e) => {
                diag.push_error(
                    "Only show(), show-modal() and hide() can be called on a Dialog from the enclosing component".into(),
                    span,
                );
            }
            Expression::FunctionCall { source_location: Some(location), .. } => {
                expr.visit(|e| check(e, dialog_element, location, diag))
            }
            _ => expr.visit(|e| check(e, dialog_element, span, diag)),
        }
    }
    recurse_elem_including_sub_components_no_borrow(parent_component, &(), &mut |elem, _| {
        let span = elem.borrow().to_source_location();
        visit_element_expressions(elem, |exp, _, _| check(exp, dialog_element, &span, diag));
    });
}

/// A Dialog can't show itself: it only exists while it's shown.
pub(super) fn check_dialog_not_shown_from_inside(
    dialog_component: &Rc<Component>,
    diag: &mut BuildDiagnostics,
) {
    let root = &dialog_component.root_element;
    recurse_elem_no_borrow(root, &(), &mut |elem, _| {
        visit_element_expressions(elem, |exp, _, _| {
            exp.visit_recursive(&mut |e| {
                if let Expression::FunctionCall { function, arguments, source_location } = e
                    && matches!(
                        function,
                        crate::expression_tree::Callable::Builtin(
                            BuiltinFunction::ShowDialog | BuiltinFunction::ShowDialogModal
                        )
                    )
                    && matches!(arguments.as_slice(), [Expression::ElementReference(e), ..] if e.upgrade().is_some_and(|e| Rc::ptr_eq(&e, root)))
                {
                    diag.push_error(
                        "A Dialog cannot show itself, call 'show()' or 'show-modal()' from the component that declares it".into(),
                        source_location,
                    );
                }
            });
        });
    });
}

/// Lay out the main widget of a `Dialog` and its buttons, in the platform's button order.
pub fn lower_dialog_layout(
    dialog_element: &ElementRc,
    style_metrics: &Rc<Component>,
    diag: &mut BuildDiagnostics,
) {
    let mut grid = GridLayout {
        elems: Default::default(),
        geometry: LayoutGeometry::new(dialog_element),
        dialog_button_roles: None,
        uses_auto: true,
    };
    let metrics = &style_metrics.root_element;
    grid.geometry
        .padding
        .bottom
        .get_or_insert(NamedReference::new(metrics, SmolStr::new_static("layout-padding")));
    grid.geometry
        .padding
        .top
        .get_or_insert(NamedReference::new(metrics, SmolStr::new_static("layout-padding")));
    grid.geometry
        .padding
        .left
        .get_or_insert(NamedReference::new(metrics, SmolStr::new_static("layout-padding")));
    grid.geometry
        .padding
        .right
        .get_or_insert(NamedReference::new(metrics, SmolStr::new_static("layout-padding")));
    grid.geometry
        .spacing
        .horizontal
        .get_or_insert(NamedReference::new(metrics, SmolStr::new_static("layout-spacing")));
    grid.geometry
        .spacing
        .vertical
        .get_or_insert(NamedReference::new(metrics, SmolStr::new_static("layout-spacing")));

    let layout_organized_data_prop = create_new_prop(
        dialog_element,
        SmolStr::new_static("layout-organized-data"),
        Type::ArrayOfU16,
    );
    let layout_cache_prop_h =
        create_new_prop(dialog_element, SmolStr::new_static("layout-cache-h"), Type::ArrayOfCoord);
    let layout_cache_prop_v =
        create_new_prop(dialog_element, SmolStr::new_static("layout-cache-v"), Type::ArrayOfCoord);
    let layout_info_prop_h = create_new_prop(
        dialog_element,
        SmolStr::new_static("layoutinfo-h"),
        layout_info_type().into(),
    );
    let layout_info_prop_v = create_new_prop(
        dialog_element,
        SmolStr::new_static("layoutinfo-v"),
        layout_info_type().into(),
    );

    let mut main_widget = None;
    let mut reject_button = None;
    let mut button_roles = Vec::new();
    let mut seen_buttons = HashSet::new();
    let mut num_cached_items: usize = 0;
    let layout_children = std::mem::take(&mut dialog_element.borrow_mut().children);
    for layout_child in &layout_children {
        let dialog_button_role_binding =
            layout_child.borrow_mut().take_binding("dialog-button-role");
        let is_button = if let Some(role_binding) = dialog_button_role_binding {
            if let Expression::EnumerationValue(val) = role_binding.expression.ignore_debug_hooks()
            {
                let en = &val.enumeration;
                debug_assert_eq!(en.name, "DialogButtonRole");
                button_roles.push(en.values[val.value].clone());
                if val.value == 0 {
                    diag.push_error(
                        "The `dialog-button-role` cannot be set explicitly to none".into(),
                        &role_binding,
                    );
                }
            } else {
                diag.push_error(
                    "The `dialog-button-role` property must be known at compile-time".into(),
                    &role_binding,
                );
            }
            if crate::passes::lower_layout::is_standard_button(&layout_child.borrow()) {
                diag.push_warning(
                    "'dialog-button-role' overrides the role that a 'StandardButton' gets from its 'kind': remove it, or use a 'Button' for a custom role".into(),
                    &role_binding,
                );
            }
            true
        } else if crate::passes::lower_layout::is_standard_button(&layout_child.borrow()) {
            // layout_child is a StandardButton
            match layout_child.borrow().binding("kind") {
                None => diag.push_error(
                    "The `kind` property of the StandardButton in a Dialog must be set".into(),
                    &*layout_child.borrow(),
                ),
                Some(binding) => {
                    if let Expression::EnumerationValue(val) =
                        binding.expression.ignore_debug_hooks()
                    {
                        let en = &val.enumeration;
                        debug_assert_eq!(en.name, "StandardButtonKind");
                        let kind = &en.values[val.value];
                        let role = match kind.as_str() {
                            "ok" => "accept",
                            "cancel" => "reject",
                            "apply" => "apply",
                            "close" => "reject",
                            "reset" => "reset",
                            "help" => "help",
                            "yes" => "accept",
                            "no" => "reject",
                            "abort" => "reject",
                            "retry" => "accept",
                            "ignore" => "accept",
                            _ => unreachable!(),
                        };
                        button_roles.push(role.into());
                        if !seen_buttons.insert(val.value) {
                            diag.push_error("Duplicated `kind`: There are two StandardButton in this Dialog with the same kind".into(), &*binding);
                        } else if Rc::ptr_eq(
                            dialog_element,
                            &dialog_element
                                .borrow()
                                .enclosing_component
                                .upgrade()
                                .unwrap()
                                .root_element,
                        ) {
                            let clicked_ty = layout_child
                                .borrow()
                                .lookup_property("clicked", PropertyLookupMode::ComponentLocal)
                                .property_type;
                            if matches!(&clicked_ty, Type::Callback { .. })
                                && layout_child.borrow().binding("clicked").is_none_or(|c| {
                                    matches!(c.value_expression(), Expression::Invalid)
                                })
                            {
                                dialog_element
                                    .borrow_mut()
                                    .property_declarations
                                    .entry(format_smolstr!("{}-clicked", kind))
                                    .or_insert_with(|| PropertyDeclaration {
                                        property_type: clicked_ty,
                                        node: None,
                                        expose_in_public_api: true,
                                        is_alias: Some(NamedReference::new(
                                            layout_child,
                                            SmolStr::new_static("clicked"),
                                        )),
                                        visibility: PropertyVisibility::InOut,
                                        pure: None,
                                        shadowed_name: None,
                                        shadowable: false,
                                        testable: false,
                                        moved_from: None,
                                        deprecated: None,
                                        synthesized: false,
                                    });
                            }
                        }
                    } else {
                        diag.push_error(
                            "The `kind` property of the StandardButton in a Dialog must be known at compile-time"
                                .into(),
                            &*binding,
                        );
                    }
                }
            }
            true
        } else {
            false
        };

        if is_button
            && reject_button.is_none()
            && button_roles.last().is_some_and(|r| r == "reject")
        {
            reject_button = Some(layout_child.clone());
        }
        if is_button {
            grid.add_element_with_coord(
                layout_child,
                (1, button_roles.len() as u16),
                (1, 1),
                &layout_cache_prop_h,
                &layout_cache_prop_v,
                &layout_organized_data_prop,
                diag,
                &mut num_cached_items,
            );
        } else if main_widget.is_some() {
            diag.push_error(
                "A Dialog can have only one child element that is not a StandardButton".into(),
                &*layout_child.borrow(),
            );
        } else {
            main_widget = Some(layout_child.clone())
        }
    }
    dialog_element.borrow_mut().children = layout_children;

    if let Some(reject_button) = reject_button
        && matches!(
            reject_button
                .borrow()
                .lookup_property("clicked", PropertyLookupMode::ComponentLocal)
                .property_type,
            Type::Callback(_)
        )
        && !dialog_element.borrow().is_binding_set("rejected", false)
    {
        let click = Expression::CodeBlock(vec![Expression::FunctionCall {
            function: Callable::Callback(NamedReference::new(
                &reject_button,
                SmolStr::new_static("clicked"),
            )),
            arguments: vec![],
            source_location: None,
        }]);
        dialog_element.borrow_mut().set_binding(SmolStr::new_static("rejected"), click.into());
    }

    if let Some(main_widget) = main_widget {
        grid.add_element_with_coord(
            &main_widget,
            (0, 0),
            (1, button_roles.len() as u16 + 1),
            &layout_cache_prop_h,
            &layout_cache_prop_v,
            &layout_organized_data_prop,
            diag,
            &mut num_cached_items,
        );
    } else {
        diag.push_error(
            "A Dialog must have a single child element that is not StandardButton".into(),
            &*dialog_element.borrow(),
        );
    }
    grid.dialog_button_roles = Some(button_roles);

    let span = dialog_element.borrow().to_source_location();
    layout_organized_data_prop.element().borrow_mut().set_binding(
        layout_organized_data_prop.name().clone(),
        BindingExpression::new_with_span(
            Expression::OrganizeGridLayout(grid.clone()),
            span.clone(),
        ),
    );
    layout_cache_prop_h.element().borrow_mut().set_binding(
        layout_cache_prop_h.name().clone(),
        BindingExpression::new_with_span(
            Expression::SolveGridLayout {
                layout_organized_data_prop: layout_organized_data_prop.clone(),
                layout: grid.clone(),
                orientation: Orientation::Horizontal,
            },
            span.clone(),
        ),
    );
    layout_cache_prop_v.element().borrow_mut().set_binding(
        layout_cache_prop_v.name().clone(),
        BindingExpression::new_with_span(
            Expression::SolveGridLayout {
                layout_organized_data_prop: layout_organized_data_prop.clone(),
                layout: grid.clone(),
                orientation: Orientation::Vertical,
            },
            span.clone(),
        ),
    );
    layout_info_prop_h.element().borrow_mut().set_binding(
        layout_info_prop_h.name().clone(),
        BindingExpression::new_with_span(
            Expression::ComputeGridLayoutInfo {
                layout_organized_data_prop: layout_organized_data_prop.clone(),
                layout: grid.clone(),
                orientation: Orientation::Horizontal,
                cross_axis_size: None,
            },
            span.clone(),
        ),
    );
    layout_info_prop_v.element().borrow_mut().set_binding(
        layout_info_prop_v.name().clone(),
        BindingExpression::new_with_span(
            Expression::ComputeGridLayoutInfo {
                layout_organized_data_prop: layout_organized_data_prop.clone(),
                layout: grid.clone(),
                orientation: Orientation::Vertical,
                cross_axis_size: None,
            },
            span,
        ),
    );
    dialog_element.borrow_mut().layout_info_prop = Some((layout_info_prop_h, layout_info_prop_v));
    for d in dialog_element.borrow_mut().debug.iter_mut() {
        d.layout = Some(Layout::GridLayout(grid.clone()));
    }
}
