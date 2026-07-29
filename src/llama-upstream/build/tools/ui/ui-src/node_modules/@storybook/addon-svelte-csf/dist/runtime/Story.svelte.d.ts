import type { Snippet } from 'svelte';
import type { Cmp, StoryAnnotations, StoryContext } from '../types.js';
declare class __sveltets_Render<TArgs extends Record<string, any>, TCmp extends Cmp, TChildren extends Snippet = Snippet> {
    props(): Partial<StoryAnnotations<TArgs, TCmp>> & {
        /**
         * @deprecated
         * Use `exportName` instead.
         */
        id?: never;
        /**
         * Name of the story. Can be omitted if `exportName` is provided.
         */
        name?: string;
        /**
         * exportName of the story.
         * If not provided, it will be generated from the 'name', by converting it to a valid, PascalCased JS variable name.
         * eg. 'My story!' -> 'MyStory'
         *
         * Use this prop to explicitly set the export name of the story. This is useful if you have multiple stories with the names
         * that result in duplicate export names like "My story" and "My story!".
         * It's also useful for explicitly defining the export that can be imported in MDX docs.
         */
        exportName?: string;
        /**
         * @deprecrated
         * Use `tags={['autodocs']}` instead.
         * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/main/MIGRATION.md#story-prop-autodocs-has-been-removed}
         */
        autodocs?: never;
        /**
         * @deprecated
         * Use `parameters={{ docs: { source: { code: "..." } } }}` instead.
         * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/next/MIGRATION.md#story-prop-source-has-been-removed}
         */
        source?: never;
    } & (({
        /**
         * exportName of the story.
         * If not provided, it will be generated from the 'name', by converting it to a valid, PascalCased JS variable name.
         * eg. 'My story!' -> 'MyStory'
         *
         * Use this prop to explicitly set the export name of the story. This is useful if you have multiple stories with the names
         * that result in duplicate export names like "My story" and "My story!".
         * It's also useful for explicitly defining the export that can be imported in MDX docs.
         */
        exportName: string;
    } | {
        /**
         * Name of the story. Can be omitted if `exportName` is provided.
         */
        name: string;
    }) & ({
        /**
         * Children to pass to the story's component
         * Or if `asChild` is true, the content to render in the story as **static** markup.
         */
        children?: TChildren | undefined;
        /**
         * Make the children the actual story content. This is useful when you want to create a **static story**.
         */
        asChild?: boolean;
        template?: never;
    } | {
        children?: never;
        asChild?: never;
        /**
         * The content to render in the story with a snippet taking `args` and `storyContext` as parameters
         *
         * NOTE: Can be omitted if a default template is set with [`render`](https://github.com/storybookjs/addon-svelte-csf/blob/main/README.md#default-snippet)
         */
        template?: Snippet<[TArgs, StoryContext<TArgs>]> | undefined;
    }));
    events(): {};
    slots(): {};
    bindings(): "";
    exports(): {};
}
interface $$IsomorphicComponent {
    new <TArgs extends Record<string, any>, TCmp extends Cmp, TChildren extends Snippet = Snippet>(options: import('svelte').ComponentConstructorOptions<ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['props']>>): import('svelte').SvelteComponent<ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['props']>, ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['events']>, ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['slots']>> & {
        $$bindings?: ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['bindings']>;
    } & ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['exports']>;
    <TArgs extends Record<string, any>, TCmp extends Cmp, TChildren extends Snippet = Snippet>(internal: unknown, props: ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['props']> & {}): ReturnType<__sveltets_Render<TArgs, TCmp, TChildren>['exports']>;
    z_$$bindings?: ReturnType<__sveltets_Render<any, any, any>['bindings']>;
}
declare const Story: $$IsomorphicComponent;
type Story<TArgs extends Record<string, any>, TCmp extends Cmp, TChildren extends Snippet = Snippet> = InstanceType<typeof Story<TArgs, TCmp, TChildren>>;
export default Story;
