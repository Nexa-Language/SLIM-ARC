/**
 * @example storyIdToExportName('some-story') => 'SomeStory'
 */
export declare const storyIdToExportName: (storyId: string) => string;
/**
 * @example exportNameToStoryId('SomeStory') => 'some-story'
 */
export declare const exportNameToStoryId: (exportName: string) => string;
/**
 * @example storyNameToId('Some Long Story Name!') => 'some-long-story-name'
 */
export declare const storyNameToId: (name: string) => string;
/**
 * @example storyNameToExportName('Some Long Story Name!') => 'SomeLongStoryName'
 */
export declare const storyNameToExportName: (name: string) => string;
/**
 * Check if a string is a valid JavaScript variable name
 * @example isValidVariableName('SomeStory') => true
 * @example isValidVariableName('Some_Story') => true
 * @example isValidVariableName('Some Story') => false
 * @example isValidVariableName('Some-Story') => false
 * @example isValidVariableName('default') => false
 *
 * @see https://github.com/shinnn/is-var-name
 */
export declare const isValidVariableName: (str: string) => boolean;
/**
 * Function to convert a non valid string template name to a valid identifier preventing
 * clashing with other templates with similar names.
 *
 * Stolen with 🧡 from the svelte codebase by @paoloricciuti
 *
 * @param str the template name
 * @returns a hash based on the content of the initial string which is a valid identifier
 */
export declare function hashTemplateName(str: string): string;
