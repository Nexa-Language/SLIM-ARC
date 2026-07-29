import type * as ESTreeAST from 'estree';
import { type AST as SvelteAST } from 'svelte/compiler';
interface GetSvelteASTOptions {
    code: string;
    filename?: string;
}
export declare function getSvelteAST(options: GetSvelteASTOptions): SvelteAST.Root;
/**
 * Create Svelte compliant AST node for {@link SvelteAST.Attibute} with optional value.
 * By default it will create an shorthand attribute.
 */
export declare function createASTAttribute(name: string, value?: SvelteAST.Attribute['value']): SvelteAST.Attribute;
/**
 * Create Svelte compliant AST node for {@link SvelteAST.ExpressionTag} with optional value.
 * By default it will create an shorthand attribute.
 */
export declare function createASTExpressionTag(expression: SvelteAST.ExpressionTag['expression']): SvelteAST.ExpressionTag;
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.Property}
 */
export declare function createASTProperty(name: string, value: ESTreeAST.Property['value']): ESTreeAST.Property;
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.ArrayExpression} with optional array of elements.
 * By default it will create an empty array.
 */
export declare function createASTArrayExpression(elements?: ESTreeAST.ArrayExpression['elements']): ESTreeAST.ArrayExpression;
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.ObjectExpression} with optional array of properties.
 * By default it will create an empty object.
 */
export declare function createASTObjectExpression(properties?: ESTreeAST.ObjectExpression['properties']): ESTreeAST.ObjectExpression;
interface ASTScriptOptions {
    module?: boolean;
    content: SvelteAST.Script['content'];
}
export declare function createASTScript(options: ASTScriptOptions): SvelteAST.Script;
/**
 * Create ESTree compliant AST node for {@link ESTreeAST.Identifier}.
 */
export declare function createASTIdentifier(name: string): ESTreeAST.Identifier;
interface ExportSpecifierOptions {
    local: string;
    exported?: string;
}
export declare function createASTExportSpecifier({ local, exported, }: ExportSpecifierOptions): ESTreeAST.ExportSpecifier;
export type { ESTreeAST, SvelteAST };
