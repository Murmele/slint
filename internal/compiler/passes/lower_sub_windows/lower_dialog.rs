// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! Lowering of a `Dialog` declared within another component, which gets its own window when shown.

use super::{check_no_reference_to_sub_window, detach_root_position};
use crate::builtin_functions::BuiltinFunction;
use crate::diagnostics::{BuildDiagnostics, SourceLocation, Spanned};
use crate::expression_tree::Expression;
use crate::object_tree::*;
use by_address::ByAddress;
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
