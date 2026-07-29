import type { Slots, StoryProps } from '../legacy-types.d.ts';
interface $$__sveltets_2_IsomorphicComponent<Props extends Record<string, any> = any, Events extends Record<string, any> = any, Slots extends Record<string, any> = any, Exports = {}, Bindings = string> {
    new (options: import('svelte').ComponentConstructorOptions<Props>): import('svelte').SvelteComponent<Props, Events, Slots> & {
        $$bindings?: Bindings;
    } & Exports;
    (internal: unknown, props: {
        $$events?: Events;
        $$slots?: Slots;
    }): Exports & {
        $set?: any;
        $on?: any;
    };
    z_$$bindings?: Bindings;
}
type $$__sveltets_2_PropsWithChildren<Props, Slots> = Props & (Slots extends {
    default: any;
} ? Props extends Record<string, never> ? any : {
    children?: any;
} : {});
/**
 * This component is to support deprecated legacy component - `Story`,
 * and this component functionality is just a "mock".
 * E.g. to allow user still have typing experience.
 * Vite pre-transform hook does codemod where this component gets transformed into new `Story` component destrucutred from `defineMeta`.
 *
 * @deprecated
 * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/main/MIGRATION.md#export-meta-removed-in-favor-of-definemeta}
 */
declare const LegacyStory: $$__sveltets_2_IsomorphicComponent<$$__sveltets_2_PropsWithChildren<StoryProps, Slots>, {
    [evt: string]: CustomEvent<any>;
}, Slots, {}, string>;
type LegacyStory = InstanceType<typeof LegacyStory>;
export default LegacyStory;
