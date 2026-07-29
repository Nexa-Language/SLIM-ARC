import {
  entry_preview_exports,
  renderToCanvas
} from "./_browser-chunks/chunk-QEV3A2KO.js";
import "./_browser-chunks/chunk-4BE7D4DS.js";

// src/globals.ts
globalThis.STORYBOOK_ENV = "svelte";

// src/portable-stories.ts
import PreviewRender from "@storybook/svelte/internal/PreviewRender.svelte";
import { createReactiveProps } from "@storybook/svelte/internal/createReactiveProps";
import {
  composeStories as originalComposeStories,
  composeStory as originalComposeStory,
  setProjectAnnotations as originalSetProjectAnnotations,
  setDefaultProjectAnnotations
} from "storybook/preview-api";
function setProjectAnnotations(projectAnnotations) {
  return setDefaultProjectAnnotations(INTERNAL_DEFAULT_PROJECT_ANNOTATIONS), originalSetProjectAnnotations(
    projectAnnotations
  );
}
var INTERNAL_DEFAULT_PROJECT_ANNOTATIONS = {
  ...entry_preview_exports,
  /** @deprecated */
  renderToCanvas: (renderContext, canvasElement) => {
    if (renderContext.storyContext.testingLibraryRender == null)
      return renderToCanvas(renderContext, canvasElement);
    let {
      storyFn,
      storyContext: { testingLibraryRender: render }
    } = renderContext, { Component, props } = storyFn(), { unmount } = render(Component, { props, target: canvasElement });
    return unmount;
  }
};
function composeStory(story, componentAnnotations, projectAnnotations, exportsName) {
  let composedStory = originalComposeStory(
    story,
    // @ts-expect-error Fix this later: Type 'Partial<{ [x: string]: any; }>' is not assignable to type 'Partial<Simplify<TArgs, {}>>'
    componentAnnotations,
    projectAnnotations,
    globalThis.globalProjectAnnotations ?? INTERNAL_DEFAULT_PROJECT_ANNOTATIONS,
    exportsName
  ), props = createReactiveProps({
    storyFn: composedStory,
    storyContext: { ...composedStory },
    name: composedStory.storyName,
    title: composedStory.id,
    showError: () => {
    }
  }), renderable = {
    Component: PreviewRender,
    props
  };
  return Object.assign(renderable, composedStory), renderable;
}
function composeStories(csfExports, projectAnnotations) {
  return originalComposeStories(csfExports, projectAnnotations, composeStory);
}
export {
  INTERNAL_DEFAULT_PROJECT_ANNOTATIONS,
  composeStories,
  composeStory,
  setProjectAnnotations
};
