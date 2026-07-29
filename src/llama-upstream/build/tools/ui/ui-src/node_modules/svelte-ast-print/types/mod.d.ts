declare module 'svelte-ast-print' {
	import type { Node as ESTreeNode } from 'estree';
	import type { AST } from 'svelte/compiler';
   /**
	* Print AST {@link SvelteAST.BaseNode} as a string.
	* Aka parse in reverse.
	*
	* ## How does it work under the hood?
	*
	* 1. Firstly, it determines whether the provided AST node is unique node for Svelte {@link SvelteAST.Node}.
	* 2. Based on type check guard from above:
	*    - it uses either this package's {@link Printer} to print Svelte AST node,
	*    - otherwise it uses `esrap` {@link print_es} to print ESTree specification-complaint AST node
	*
	* ## How to use it?
	*
	* @example writing a codemode using Node.js
	  ```js
	  import fs from "node:fs";

	  import { print } from "svelte-ast-print";
	  import { parse } from "svelte/compiler";

	  const originalSvelteCode = fs.readFileSync("src/App.svelte", "utf-8");
	  let svelteAST = parse(originalSvelteCode, { modern: true });
	  //                                          👆 For now, only modern is supported.
	  //                                             By default is 'false'.
	  //                                             Is it planned to be 'true' from Svelte v6+

	  // ...
	  // Do some modifications on this AST...
	  // e.g. transform `<slot />` to `{@render children()}`
	  // ...

	  const output = print(svelteAST); // AST is now a stringified code output! 🎉

	  fs.writeFileSync("src/App.svelte", output, { encoding: " utf-8" });
	  ```
	*
	* @param node - Svelte or ESTree AST node
	* @param options - printing options
	* @returns Stringified Svelte AST node
	* TODO: Ask Svelte maintainers if `Script` and `SvelteOptions` were omittted from `SvelteNode` intentionally - possibly forgotten to include
	*/
   export function print(node: Node, options?: Partial<ConstructorParameters<typeof Options>[0]>): string;
	export function isAttributeLikeNode(node: SvelteNode): node is AttributeLike;
	export function isBlockNode(node: SvelteNode): node is Block;
	export function isCssNode(node: SvelteNode): node is AST.Css.Node;
	export function isElementLikeNode(node: SvelteNode): node is ElementLike;
	export function isHtmlNode(node: SvelteNode): node is HtmlNode;
	export function isTagNode(node: SvelteNode): node is Tag;
	export function isTemplateNode(node: SvelteNode): node is TemplateNode;
	export function isSvelteNode(node: Node): node is SupportedSvelteNode;
	/**
	 * TODO: Svelte could expose this type to public too: https://github.com/sveltejs/svelte/blob/2b362ddc63e930726b67a1010d2829a3a4f6bb85/packages/svelte/src/compiler/types/template.d.ts#L514
	 * FIXME: Include `Css.Node` when exposed to public
	 */
	type SvelteNode = ESTreeNode | TemplateNode | AST.Fragment;
	/**
	 * TODO: Svelte could expose this type to public too: https://github.com/sveltejs/svelte/blob/2b362ddc63e930726b67a1010d2829a3a4f6bb85/packages/svelte/src/compiler/types/template.d.ts#L476
	 */
	type Directive = AST.AnimateDirective | AST.BindDirective | AST.ClassDirective | AST.LetDirective | AST.OnDirective | AST.SpreadAttribute | AST.StyleDirective | AST.TransitionDirective | AST.UseDirective;
	type AttributeLike = AST.Attribute | AST.SpreadAttribute | Directive;
	/**
	 * TODO: Svelte could expose this type to public too: https://github.com/sveltejs/svelte/blob/2b362ddc63e930726b67a1010d2829a3a4f6bb85/packages/svelte/src/compiler/types/template.d.ts#L486
	 */
	type Block = AST.EachBlock | AST.IfBlock | AST.AwaitBlock | AST.KeyBlock | AST.SnippetBlock;
	/**
	 * TODO: Svelte could expose this type to public too: https://github.com/sveltejs/svelte/blob/2b362ddc63e930726b67a1010d2829a3a4f6bb85/packages/svelte/src/compiler/types/template.d.ts#L488
	 */
	type ElementLike = AST.Component | AST.TitleElement | AST.SlotElement | AST.RegularElement | AST.SvelteBody | AST.SvelteComponent | AST.SvelteDocument | AST.SvelteElement | AST.SvelteFragment | AST.SvelteHead | AST.SvelteOptionsRaw | AST.SvelteSelf | AST.SvelteWindow;
	type HtmlNode = AST.Comment | AST.Text;
	/**
	 * TODO: Svelte could expose this type to public too: https://github.com/sveltejs/svelte/blob/2b362ddc63e930726b67a1010d2829a3a4f6bb85/packages/svelte/src/compiler/types/template.d.ts#L474
	 */
	type Tag = AST.ExpressionTag | AST.HtmlTag | AST.ConstTag | AST.DebugTag | AST.RenderTag;
	/**
	 * TODO: Svelte could expose this type to public too: https://github.com/sveltejs/svelte/blob/2b362ddc63e930726b67a1010d2829a3a4f6bb85/packages/svelte/src/compiler/types/template.d.ts#L503
	 */
	type TemplateNode = AST.Root | AST.Text | Tag | ElementLike | AST.Attribute | AST.SpreadAttribute | Directive | AST.Comment | Block;
	/**
	 * Not all of the nodes are bundled together with {@link AST.BaseNode}.
	 * This type wraps them together as supported ones for printing.
	 */
	type SupportedSvelteNode = AST.Script | AST.BaseNode | AST.SvelteOptionsRaw | SvelteNode;
	/**
	 * Bundle together Svelte and ESTree specification complaint nodes, so we can support printing both.
	 */
	type Node = ESTreeNode | SupportedSvelteNode;
	/**
	 * This class is for internal use only.
	 * Give sa a better control on transforming passed options to the second argument of {@link print}
	 *
	 * */
	class Options {
		static INDENT: Map<"tab" | "2-space" | "4-space", "\t" | "  " | "    ">;
		/**
		 * @param raw - provided options by user - before transformation
		 */
		constructor(raw: PrintOptions);
		get indent(): "\t" | "  " | "    ";
		
		get order(): readonly [never, never, never, never, never];
		#private;
	}
	/**
	 * Options for {@link print} defined by user.
	 */
	type PrintOptions = {
		/**
		 * - formatting options
		 */
		format?: Partial<FormatOptions> | undefined;
		/**
		 * - Svelte AST node {@link Root} based options
		 */
		root?: Partial<RootOptions> | undefined;
	};
	/**
	 * Options related to formatting.
	 * Provided for building a stable API - gives an space for expansion on future improvements/features.
	 */
	type FormatOptions = {
		/**
		 * - defaults to {@link DEFAULT_INDENT}
		 */
		indent?: "tab" | "2-space" | "4-space" | undefined;
	};
	/**
	 * Options related to {@link Root} Svelte AST node.
	 */
	type RootOptions = {
		/**
		 * - defaults to {@link DEFAULT_ORDER}
		 */
		order?: readonly [never, never, never, never, never] | undefined;
	};

	export {};
}

//# sourceMappingURL=mod.d.ts.map