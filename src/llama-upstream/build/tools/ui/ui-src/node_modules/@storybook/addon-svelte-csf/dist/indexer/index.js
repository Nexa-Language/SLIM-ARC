import { parseForIndexer } from './parser.js';
import { GetDefineMetaFirstArgumentError, IndexerParseError, MissingModuleTagError, NoStoryComponentDestructuredError, } from '../utils/error/parser/extract/svelte.js';
import { LegacyTemplateNotEnabledError } from '../utils/error/legacy-api/index.js';
import { NoDestructuredDefineMetaCallError } from '../utils/error/parser/analyse/define-meta.js';
import { isStorybookSvelteCSFError } from '../utils/error.js';
import { SVELTE_CSF_V4_TAG, SVELTE_CSF_V5_TAG } from '../constants.js';
export const createIndexer = (legacyTemplate) => ({
    test: /\.svelte$/,
    createIndex: async (filename, { makeTitle }) => {
        try {
            const { meta, stories, isLegacy } = await parseForIndexer(filename, {
                legacyTemplate,
            });
            return stories.map((story) => {
                return {
                    type: 'story',
                    importPath: filename,
                    exportName: story.exportName,
                    name: story.name,
                    title: makeTitle(meta.title),
                    tags: [
                        ...(meta.tags ?? []),
                        ...(story.tags ?? []),
                        isLegacy ? SVELTE_CSF_V4_TAG : SVELTE_CSF_V5_TAG,
                    ],
                };
            });
        }
        catch (error) {
            if (
            // NOTE: Those errors are hand-picked from what might be thrown in `./parser.ts`
            // and are related to using legacy API.
            error instanceof MissingModuleTagError ||
                error instanceof NoDestructuredDefineMetaCallError ||
                error instanceof NoStoryComponentDestructuredError ||
                error instanceof GetDefineMetaFirstArgumentError) {
                const { filename } = error;
                throw new LegacyTemplateNotEnabledError(filename, { cause: error });
            }
            // WARN: We can't use `instanceof StorybookSvelteCSFError`, because is an _abstract_ class
            if (isStorybookSvelteCSFError(error)) {
                throw error;
            }
            throw new IndexerParseError({ cause: error });
        }
    },
});
