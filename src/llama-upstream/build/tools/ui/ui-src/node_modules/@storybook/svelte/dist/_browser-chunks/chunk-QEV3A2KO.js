import {
  __export
} from "./chunk-4BE7D4DS.js";

// src/entry-preview.ts
var entry_preview_exports = {};
__export(entry_preview_exports, {
  applyDecorators: () => decorateStory,
  argTypesEnhancers: () => argTypesEnhancers,
  mount: () => mount2,
  parameters: () => parameters,
  render: () => render,
  renderToCanvas: () => renderToCanvas
});
import { enhanceArgTypes } from "storybook/internal/docs-tools";

// src/extractArgTypes.ts
import { logger } from "storybook/internal/client-logger";
function hasKeyword(keyword, keywords) {
  return keywords ? keywords.find((k) => k.name === keyword) != null : !1;
}
var extractArgTypes = (component) => {
  try {
    let docgen = component.__docgen;
    if (docgen)
      return createArgTypes(docgen);
  } catch (err) {
    logger.log(`Error extracting argTypes: ${err}`);
  }
  return {};
}, createArgTypes = (docgen) => {
  let results = {};
  return docgen.data && docgen.data.forEach((item) => {
    results[item.name] = {
      ...parseTypeToControl(item.type),
      name: item.name,
      description: item.description || void 0,
      type: {
        required: hasKeyword("required", item.keywords || []),
        name: item.type?.text === "{}" ? "object" : item.type?.text
      },
      table: {
        type: {
          summary: item.type?.text
        },
        defaultValue: {
          summary: item.defaultValue
        },
        category: "properties"
      }
    };
  }), docgen.events && docgen.events.forEach((item) => {
    results[`event_${item.name}`] = {
      name: item.name,
      action: item.name,
      control: !1,
      ...item.description ? { description: item.description } : {},
      table: {
        category: "events"
      }
    };
  }), docgen.slots && docgen.slots.forEach((item) => {
    results[`slot_${item.name}`] = {
      name: item.name,
      control: !1,
      description: [item.description, item.params?.map((p) => `\`${p.name}\``).join(" ")].filter((p) => p).join(`

`),
      table: {
        category: "slots"
      }
    };
  }), results;
}, parseTypeToControl = (type) => {
  if (!type)
    return null;
  if (type.kind === "type")
    switch (type.type) {
      case "string":
        return { control: { type: "text" } };
      case "any":
        return { control: { type: "object" } };
      default:
        return { control: { type: type.type } };
    }
  else if (type.kind === "union") {
    if (Array.isArray(type.type) && !type.type.some(
      (t) => t.kind !== "const" || !["string", "number", "null", "undefined"].includes(t.type)
    )) {
      let options = type.type.map((t) => t.value);
      return {
        control: {
          type: "radio"
        },
        options
      };
    }
  } else if (type.kind === "function")
    return { control: null };
  return null;
};

// src/extractComponentDescription.ts
function extractComponentDescription(component) {
  return component?.__docgen?.description || "";
}

// src/render.ts
import { RESET_STORY_ARGS } from "storybook/internal/core-events";
import PreviewRender from "@storybook/svelte/internal/PreviewRender.svelte";
import { createReactiveProps } from "@storybook/svelte/internal/createReactiveProps";
import { addons } from "storybook/preview-api";
import * as svelte from "svelte";
var storyIdsToRemountFromResetArgsEvent = /* @__PURE__ */ new Set();
addons.getChannel().on(RESET_STORY_ARGS, ({ storyId }) => {
  storyIdsToRemountFromResetArgsEvent.add(storyId);
});
var componentsByDomElement = /* @__PURE__ */ new Map();
async function renderToCanvas({
  storyFn,
  title,
  name,
  showMain,
  showError,
  storyContext,
  forceRemount
}, canvasElement) {
  function unmount2(canvasElementToUnmount) {
    let { mountedComponent } = componentsByDomElement.get(canvasElementToUnmount) ?? {};
    mountedComponent && (svelte.unmount(mountedComponent), componentsByDomElement.delete(canvasElementToUnmount));
  }
  let existingComponent = componentsByDomElement.get(canvasElement), remount = forceRemount;
  if (storyIdsToRemountFromResetArgsEvent.has(storyContext.id) && (remount = !0, storyIdsToRemountFromResetArgsEvent.delete(storyContext.id)), remount && unmount2(canvasElement), !existingComponent || remount) {
    let props = createReactiveProps({
      storyFn,
      storyContext,
      name,
      title,
      showError
    }), mountedComponent = svelte.mount(PreviewRender, {
      target: canvasElement,
      props
    });
    componentsByDomElement.set(canvasElement, { mountedComponent, props }), await svelte.tick();
  } else
    Object.assign(existingComponent.props, {
      storyFn,
      storyContext,
      name,
      title,
      showError
    }), await svelte.tick();
  return showMain(), () => {
    unmount2(canvasElement);
  };
}
var render = (args, context) => {
  let { id, component: Component } = context;
  if (!Component)
    throw new Error(
      `Unable to render story ${id} as the component annotation is missing from the default export`
    );
  return { Component, props: args };
};

// src/decorators.ts
import DecoratorHandler from "@storybook/svelte/internal/DecoratorHandler.svelte";
import { sanitizeStoryContextUpdate } from "storybook/preview-api";
function unWrap(obj) {
  return obj && typeof obj == "object" && "default" in obj ? obj.default : obj;
}
function prepareStory(context, rawStory, rawInnerStory) {
  let story = unWrap(rawStory), innerStory = rawInnerStory && unWrap(rawInnerStory), preparedStory;
  return !story || Object.keys(story).length === 0 ? preparedStory = {
    Component: context.component
  } : story.Component ? preparedStory = story : preparedStory = {
    Component: story
  }, innerStory ? {
    Component: DecoratorHandler,
    props: {
      // inner stories will already have been prepared, keep as is
      ...innerStory,
      decorator: preparedStory
    }
  } : { ...preparedStory, argTypes: context.argTypes };
}
function decorateStory(storyFn, decorators) {
  return decorators.reduce(
    (decorated, decorator) => (context) => {
      let story, decoratedStory = decorator((update) => (story = decorated({
        ...context,
        ...sanitizeStoryContextUpdate(update)
      }), story), context);
      return story || (story = decorated(context)), decoratedStory === story ? story : prepareStory(context, decoratedStory, story);
    },
    (context) => prepareStory(context, storyFn(context))
  );
}

// src/mount.ts
var mount2 = (context) => async (Component, options) => (Component && (context.originalStoryFn = () => ({
  Component,
  props: options && "props" in options ? options?.props : options
})), await context.renderToCanvas(), context.canvas);

// src/entry-preview.ts
var parameters = {
  renderer: "svelte",
  docs: {
    story: { inline: !0 },
    extractArgTypes,
    extractComponentDescription
  }
}, argTypesEnhancers = [enhanceArgTypes];

export {
  renderToCanvas,
  render,
  decorateStory,
  mount2 as mount,
  parameters,
  argTypesEnhancers,
  entry_preview_exports
};
