import type { ComponentAnnotations as BaseComponentAnnotations, StoryAnnotations as BaseStoryAnnotations, StoryContext as BaseStoryContext, WebRenderer } from 'storybook/internal/types';
import type { Component, ComponentProps } from 'svelte';
export type Cmp = Component<any>;
export type ComponentAnnotations<TCmp extends Cmp, TArgs extends Record<string, any> = Record<string, any>> = BaseComponentAnnotations<SvelteRenderer<TCmp>, TArgs>;
export interface SvelteRenderer<TCmp extends Cmp> extends WebRenderer {
    component: TCmp;
    storyResult: SvelteStoryResult<TCmp>;
}
export interface SvelteStoryResult<TCmp extends Cmp> {
    Component?: TCmp;
    props?: ComponentProps<TCmp>;
    decorator?: TCmp;
}
export type StoryContext<TArgs extends Record<string, any>> = BaseStoryContext<SvelteRenderer<Component<TArgs>>, TArgs>;
export type StoryAnnotations<TArgs extends Record<string, any>, TCmp extends Cmp> = BaseStoryAnnotations<SvelteRenderer<TCmp>, TArgs, Partial<TArgs>>;
