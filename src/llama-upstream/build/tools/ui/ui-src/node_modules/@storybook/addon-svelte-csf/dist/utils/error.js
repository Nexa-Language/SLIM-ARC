import url from 'node:url';
import pkg from '@storybook/addon-svelte-csf/package.json' with { type: 'json' };
/**
 * Adopted from: {@link https://github.com/storybookjs/storybook/blob/next/code/lib/core-events/src/errors/storybook-error.ts}
 * Copied because is not exposed in the `storybook/internal/core-events` package,
 * and modified for this addon needs.
 */
export class StorybookSvelteCSFError extends Error {
    static isStorybookCSFSvelteError = true;
    static packageName = pkg.name;
    static packageVersion = pkg.version;
    static CATEGORY = {
        parserExtractSvelte: 'PARSER_EXTRACT_SVELTE',
        parserExtractCompiled: 'PARSER_EXTRACT_COMPILED',
        parserAnalyseDefineMeta: 'PARSER_ANALYSE_DEFINE_META',
        parserAnalyseStory: 'PARSER_ANALYSE_STORY',
        compiler: 'COMPILER',
        legacyAPI: 'LEGACY_API',
    };
    /**
     * Data associated with the error. Used to provide additional information in the error message or to be passed to telemetry.
     */
    data = {};
    /**
     * Specifies the documentation for the error.
     * - If `true`, links to a documentation page on the Storybook website (make sure it exists before enabling).
     * - If a string, uses the provided URL for documentation (external or FAQ links).
     * - If `false` (default), no documentation link is added.
     */
    documentation = false;
    /**
     * Flag used to easily determine if the error originates from Storybook.
     */
    fromStorybook = true;
    /**
     * Any custom message to override the default error message.
     * Vite overrides the `Error.message` property, so we support that.
     */
    customMessage;
    get fullErrorCode() {
        const paddedCode = String(this.code).padStart(4, '0');
        return `SB_SVELTE_CSF_${this.category}_${paddedCode}`;
    }
    /**
     * Overrides the default `Error.name` property in the format: SB_<CATEGORY>_<CODE>.
     */
    get name() {
        const errorName = this.constructor.name;
        return `${this.fullErrorCode} (${errorName})`;
    }
    /**
     * Generates the error message along with additional documentation link (if applicable).
     */
    get message() {
        if (this.customMessage) {
            return this.customMessage;
        }
        let page;
        if (this.documentation === true) {
            page = `https://github.com/storybookjs/addon-svelte-csf/blob/v${StorybookSvelteCSFError.packageVersion}/ERRORS.md#${this.fullErrorCode}`;
        }
        else if (typeof this.documentation === 'string') {
            page = this.documentation;
        }
        else if (Array.isArray(this.documentation)) {
            page = `\n${this.documentation.map((doc) => `\t- ${doc}`).join('\n')}`;
        }
        return `${this.template()}${page != null ? `\n\nMore info: ${page}\n` : ''}`;
    }
    /**
     * Allows anyone to set Error.message after creation, mimicking the native Error behavior.
     * Vite does this sometimes.
     */
    set message(message) {
        this.customMessage = message;
    }
    /**
     * `*.stories.svelte` file path where the error has occurred.
     */
    filename;
    /**
     * Name of the `<Story name=">...<" />` component which caused the error.
     */
    component;
    constructor({ filename, component: component, }, options) {
        super();
        this.cause = options?.cause;
        this.filename = filename;
        this.component = component;
    }
    // WARN: I had to duplicate logic. We already have functions for it.
    // But we can't import it, because it would create a cyclic-dependency.
    get storyNameFromAttribute() {
        if (!this.component) {
            return '<UnnamedComponent>';
        }
        const { attributes } = this.component;
        for (const attribute of attributes) {
            if (attribute.type !== 'Attribute') {
                // NOTE: Nothing to do with this case - invalid tbh
                continue;
            }
            if (attribute.value === true) {
                // NOTE: Nothing to do with this case - invalid tbh
                continue;
            }
            // value is SvelteAST.ExpressionTag
            if (!Array.isArray(attribute.value)) {
                return 'value' in attribute.value.expression ? attribute.value.expression.value : undefined;
            }
            if (attribute.value[0].type === 'Text') {
                return attribute.value[0].data;
            }
            if (attribute.value[0].expression.type === 'Literal' &&
                typeof attribute.value[0].expression.value === 'string') {
                return attribute.value[0].expression.value;
            }
        }
    }
    get filepathURL() {
        if (this.filename) {
            return url.pathToFileURL(this.filename);
        }
        else {
            return '<path not specified>';
        }
    }
    get quickStoryRawCodeIdentifier() {
        return `<Story name="${this.storyNameFromAttribute}" />`;
    }
}
// WARN: We can't use `instanceof StorybookSvelteCSFError`, because is an _abstract_ class
export function isStorybookSvelteCSFError(error) {
    return Boolean(Object.getPrototypeOf(error)?.constructor
        ?.isStorybookCSFSvelteError);
}
