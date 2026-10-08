use crate::diagnostics::{Diagnostic, SourceLocation, Span};
use crate::expression_tree::Callable;
use crate::langtype::Type;
use crate::typeregister;
use crate::{
    diagnostics::BuildDiagnostics,
    expression_tree::{BuiltinFunction, Expression},
    object_tree::{Component, ElementRc},
};
use std::rc::Rc;

fn is_listview_element(element: &ElementRc) -> bool {
    element.borrow().repeated.as_ref().is_some_and(|r| r.is_listview.is_some())
}

pub fn handle_listview(root_component: &Rc<Component>, diag: &mut BuildDiagnostics) {
    crate::object_tree::recurse_elem_including_sub_components(
        root_component,
        &(),
        &mut |element_rc: &ElementRc, _| {
            let element = element_rc.borrow();
            let Some(repeated) = element.repeated.as_ref() else {
                return;
            };

            let Some(is_listview) = repeated.is_listview.as_ref() else {
                return;
            };
            let nr = &is_listview.ensure_row_visible;
            let listview_elem = nr.element();
            if let Some(binding) =
                listview_elem.borrow().bindings.binding_cell_including_synthetic(nr.name())
            {
                if !matches!(&binding.borrow().expression, Expression::CodeBlock(v) if v.is_empty())
                {
                    diag.push_error(
                        "Remove the body of 'ensure-row-visible', the compiler provides it for a 'ListView'".into(),
                        &*binding.borrow(),
                    );
                    return;
                }

                binding.borrow_mut().expression = Expression::FunctionCall {
                    function: Callable::Builtin(BuiltinFunction::ListViewEnsureRowVisible),
                    arguments: vec![
                        Expression::ElementReference(Rc::downgrade(element_rc)),
                        Expression::FunctionParameterReference { index: 0, ty: Type::Int32 },
                        Expression::FunctionParameterReference {
                            index: 1,
                            ty: Type::Enumeration(typeregister::BUILTIN.enums.ScrollMode.clone()),
                        },
                    ],
                    source_location: None,
                }
            }
        },
    );
}
