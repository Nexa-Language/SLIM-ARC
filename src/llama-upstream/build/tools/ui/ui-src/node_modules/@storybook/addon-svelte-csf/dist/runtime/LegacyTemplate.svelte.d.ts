import type { Slots, TemplateProps } from '../legacy-types.d.ts';
interface $$__sveltets_2_IsomorphicComponent<Props extends Record<string, any> = any, Events extends Record<string, any> = any, Slots extends Record<string, any> = any, Exports = {}, Bindings = string> {
    new (options: import('svelte').ComponentConstructorOptions<Props>): import('svelte').SvelteComponent<Props, Events, Slots> & {
        $$bindings?: Bindings;
    } & Exports;
    (internal: unknown, props: Props & {
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
 * This component is to support deprecated legacy component - `Template`,
 * and this component functionality is just a "mock".
 * E.g. to allow user still have typing experience.
 * Vite pre-transform hook does codemod where this component gets transformed into Svelte v5 snippet block.
 *
 * @deprecated
 * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/main/MIGRATION.md#template-component-removed}
 */
declare const LegacyTemplate: $$__sveltets_2_IsomorphicComponent<$$__sveltets_2_PropsWithChildren<TemplateProps, Slots>, {
    [evt: string]: CustomEvent<any>;
}, Slots, {}, string>;
type LegacyTemplate = InstanceType<typeof LegacyTemplate>;
export default LegacyTemplate;
