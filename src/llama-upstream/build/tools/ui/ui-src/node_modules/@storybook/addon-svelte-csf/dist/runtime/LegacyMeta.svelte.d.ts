import type { MetaProps } from '../legacy-types.d.ts';
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
/**
 * This component is to support deprecated legacy component - `Meta`,
 * and this component functionality is just a "mock".
 * e.g. to allow user still have typing experience.
 * Vite pre-transform hook does codemod where this component gets transformed into `defineMeta` and inserted into script module tag.
 *
 * @deprecated
 * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/main/MIGRATION.md#meta-component-removed-in-favor-of-definemeta}
 */
declare const LegacyMeta: $$__sveltets_2_IsomorphicComponent<MetaProps, {
    [evt: string]: CustomEvent<any>;
}, {}, {}, string>;
type LegacyMeta = InstanceType<typeof LegacyMeta>;
export default LegacyMeta;
