// Copyright © SixtyFPS GmbH <info@slint.dev>
// SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0

//! This pass transforms the PopupWindow element, and a Dialog declared within another
//! component, into a component that is only instantiated while shown in its own window.

mod lower_dialog;
mod lower_popup;

pub use lower_popup::is_popup_window;

use crate::diagnostics::{BuildDiagnostics, SourceLocation, Spanned};
use crate::expression_tree::{Expression, NamedReference};
use crate::langtype::Type;
use crate::object_tree::*;
use crate::typeregister::TypeRegister;
use by_address::ByAddress;
use smol_str::{SmolStr, format_smolstr};
use std::collections::HashSet;
use std::rc::{Rc, Weak};

pub fn lower_sub_windows(
    component: &Rc<Component>,
    type_register: &TypeRegister,
    diag: &mut BuildDiagnostics,
) {
    let window_type = type_register.lookup_builtin_element("Window").unwrap();
    #[allow(clippy::mutable_key_type)]
    let mut lowered = HashSet::new();
    #[allow(clippy::mutable_key_type)]
    let shown_dialogs = lower_dialog::collect_shown_dialogs(component);

    recurse_elem_including_sub_components_no_borrow(
        component,
        &None,
        &mut |elem, parent_element: &Option<ElementRc>| {
            if is_popup_window(elem) && lowered.insert(ByAddress(elem.clone())) {
                lower_popup::lower_popup_window(elem, parent_element.as_ref(), &window_type, diag);
            } else if lower_dialog::is_dialog(elem) && lowered.insert(ByAddress(elem.clone())) {
                let enclosing = elem.borrow().enclosing_component.upgrade().unwrap();
                if parent_element.is_none() && enclosing.parent_element().is_none() {
                    // The root of a component, which is shown from native code
                    lower_dialog::check_dialog_not_shown_from_inside(&enclosing, diag);
                } else if shown_dialogs.contains(&ByAddress(elem.clone())) {
                    lower_dialog::lower_dialog(elem, parent_element.as_ref(), diag);
                }
                // Otherwise, the Dialog is only used to lay out its buttons in place.
            }
            Some(elem.clone())
        },
    )
}

/// The root of a sub-window is shown as a top-level, so its children are rendered starting with a
/// (0, 0) offset, whatever its x/y bindings. Returns a reference to the property that is now the
/// origin of the root.
fn detach_root_position(component: &Rc<Component>, prefix: &str) -> NamedReference {
    let mut root = component.root_element.borrow_mut();
    let name = format_smolstr!("{prefix}-{}-dummy", root.id);
    root.property_declarations.insert(
        name.clone(),
        PropertyDeclaration { synthesized: true, ..Type::LogicalLength.into() },
    );
    drop(root);
    let x = NamedReference::new(&component.root_element, name.clone());
    let y = NamedReference::new(&component.root_element, name);
    let mut root = component.root_element.borrow_mut();
    let geometry = root.geometry_props.as_mut().unwrap();
    geometry.x = x.clone();
    geometry.y = y;
    x
}

/// Throw error when accessing the popup or dialog from outside
// FIXME: Maybe this should actually be allowed
pub fn check_no_reference_to_sub_window(
    popup_window_element: &ElementRc,
    parent_component: &Rc<Component>,
    new_weak: &Weak<Component>,
    random_valid_ref: &NamedReference,
    diag: &mut BuildDiagnostics,
) {
    let popup_span = popup_window_element.borrow().to_source_location();
    #[allow(clippy::mutable_key_type)]
    let mut reported = HashSet::<(ByAddress<ElementRc>, SmolStr)>::new();
    let mut check = |element: &ElementRc, name: &str, span: &SourceLocation| {
        let in_popup = Weak::ptr_eq(&element.borrow().enclosing_component, new_weak);
        if in_popup && reported.insert((ByAddress(element.clone()), name.into())) {
            report_access(element, diag, popup_window_element, name, span);
        }
        in_popup
    };
    recurse_elem_including_sub_components_no_borrow(parent_component, &(), &mut |elem, _| {
        visit_element_expressions_with_location(elem, &popup_span, &mut |exp, span| {
            if let Expression::ElementReference(element) = exp {
                let elem = element.upgrade().unwrap();
                if !Rc::ptr_eq(&elem, popup_window_element) {
                    check(&elem, "", span);
                }
            } else if let Some(nr) = exp.referenced_property() {
                check(&nr.element(), nr.name(), span);
            }
        });
    });
    visit_all_named_references(parent_component, &mut |nr| {
        if check(&nr.element(), nr.name(), &popup_span) {
            // just set it to whatever is a valid NamedReference, otherwise we'll panic later
            *nr = random_valid_ref.clone();
        }
    });
}

pub fn report_access(
    element: &ElementRc,
    diag: &mut BuildDiagnostics,
    popup_window_element: &ElementRc,
    prop_name: &str,
    span: &SourceLocation,
) {
    let element_name = popup_window_element
        .borrow()
        .builtin_type()
        .map(|t| t.name.clone())
        .unwrap_or_else(|| SmolStr::new_static("PopupWindow"));
    let id = element.borrow().id.clone();
    let what = if prop_name.is_empty() {
        if id.is_empty() { "something".into() } else { format!("element '{id}'") }
    } else if id.is_empty() {
        format!("property or callback '{prop_name}'")
    } else {
        format!("property or callback '{id}.{prop_name}'")
    };

    diag.push_error(
        format!("Cannot access {what} inside of a {element_name} from enclosing component"),
        span,
    );
}
