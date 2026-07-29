import { compile } from 'svelte/compiler';
export function getSvelteAST(options) {
    const { filename, code } = options;
    const { ast } = compile(code, {
        filename,
        modernAst: true,
    });
    return ast;
}
/**
 * Create Svelte compliant AST node for {@link SvelteAST.Attibute} with optional value.
 * By default it will create an shorthand attribute.
 */
export function createASTAttribute(name, value = true) {
    return {
        type: 'Attribute',
        name,
        value,
    };
}
/**
 * Create Svelte compliant AST node for {@link SvelteAST.ExpressionTag} with optional value.
 * By default it will create an shorthand attribute.
 */
export function createASTExpressionTag(expression) {
    return {
        type: 'ExpressionTag',
        expression,
    };
}
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.Property}
 */
export function createASTProperty(name, value) {
    return {
        type: 'Property',
        kind: 'init',
        computed: false,
        method: false,
        shorthand: false,
        key: {
            type: 'Identifier',
            name,
        },
        value,
    };
}
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.ArrayExpression} with optional array of elements.
 * By default it will create an empty array.
 */
export function createASTArrayExpression(elements = []) {
    return {
        type: 'ArrayExpression',
        elements,
    };
}
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.ObjectExpression} with optional array of properties.
 * By default it will create an empty object.
 */
export function createASTObjectExpression(properties = []) {
    return {
        type: 'ObjectExpression',
        properties,
    };
}
export function createASTScript(options) {
    const { content, module = false } = options;
    const attributes = [];
    if (module) {
        attributes.push(createASTAttribute('module'));
    }
    return {
        type: 'Script',
        context: module ? 'module' : 'default',
        attributes,
        content,
    };
}
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.Identifier}.
 */
export function createASTIdentifier(name) {
    return {
        type: 'Identifier',
        name,
    };
}
export function createASTExportSpecifier({ local, exported, }) {
    return {
        type: 'ExportSpecifier',
        local: createASTIdentifier(local),
        exported: createASTIdentifier(exported ?? local),
    };
}
