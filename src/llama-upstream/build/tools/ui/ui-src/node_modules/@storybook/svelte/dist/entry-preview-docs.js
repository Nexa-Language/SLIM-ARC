import "./_browser-chunks/chunk-4BE7D4DS.js";

// src/docs/sourceDecorator.ts
import { deprecate } from "storybook/internal/client-logger";
import { SourceType } from "storybook/internal/docs-tools";
import { emitTransformCode, useEffect, useRef } from "storybook/preview-api";
var skipSourceRender = (context) => {
  let sourceParams = context?.parameters.docs?.source, isArgsStory = context?.parameters.__isArgsStory;
  return (context?.tags ?? []).some((tag) => tag.startsWith("svelte-csf")) ? !0 : sourceParams?.type === SourceType.DYNAMIC ? !1 : !isArgsStory || sourceParams?.code || sourceParams?.type === SourceType.CODE;
};
function toSvelteProperty(key, value, argTypes) {
  if (value == null)
    return null;
  let argType = argTypes[key];
  return argType && argType.defaultValue === value || argType && argType.action ? null : value === !0 ? key : typeof value == "string" ? `${key}=${JSON.stringify(value)}` : typeof value == "function" ? `${key}={<handler>}` : `${key}={${JSON.stringify(value)}}`;
}
function getComponentName(component) {
  if (component == null)
    return null;
  let { __docgen = {} } = component, { name } = __docgen;
  return name ? (name.endsWith(".svelte") && (name = name.substring(0, name.length - 7)), name) : component.name;
}
function generateSvelteSource(component, args, argTypes, slotProperty) {
  let name = getComponentName(component);
  if (!name)
    return null;
  let propsArray = Object.entries(args).filter(([k]) => k !== slotProperty).map(([k, v]) => toSvelteProperty(k, v, argTypes)).filter((p) => p), props = propsArray.join(" "), multiline = props.length > 50, slotValue = slotProperty ? args[slotProperty] : null, srcStart = multiline ? `<${name}
  ${propsArray.join(`
  `)}` : `<${name} ${props}`;
  return slotValue ? `${srcStart}>
    ${slotValue}
</${name}>` : `${srcStart}/>`;
}
function getWrapperProperties(component) {
  let { __docgen } = component || {};
  return __docgen ? __docgen.keywords?.find((kw) => kw.name === "wrapper") ? { wrapper: !0, slotProperty: __docgen.data?.find(
    (prop) => prop.keywords.find((kw) => kw.name === "slot")
  )?.name } : { wrapper: !1 } : { wrapper: !1 };
}
var sourceDecorator = (storyFn, context) => {
  let skip = skipSourceRender(context), story = storyFn(), source = useRef(void 0);
  return useEffect(() => {
    if (skip)
      return;
    let { parameters = {}, args = {}, component: ctxComponent } = context || {}, { Component: component } = context.originalStoryFn(
      args,
      context
    ), { wrapper, slotProperty } = getWrapperProperties(component);
    wrapper && (parameters.component && deprecate("parameters.component is deprecated. Using context.component instead."), component = ctxComponent);
    let generated = generateSvelteSource(component, args, context?.argTypes, slotProperty);
    generated && source.current !== generated && (emitTransformCode(generated, context), source.current = generated);
  }), story;
};

// src/entry-preview-docs.ts
var decorators = [sourceDecorator];
export {
  decorators
};
