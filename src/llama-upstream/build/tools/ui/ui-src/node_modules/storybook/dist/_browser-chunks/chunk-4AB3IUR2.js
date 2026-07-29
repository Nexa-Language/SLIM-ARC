// ../addons/docs/src/blocks/controls/helpers.ts
var getControlId = (value, storyId) => {
  let base = value.replace(/\s+/g, "-");
  return storyId ? `control-${storyId}-${base}` : `control-${base}`;
}, getControlSetterButtonId = (value, storyId) => {
  let base = value.replace(/\s+/g, "-");
  return storyId ? `set-${storyId}-${base}` : `set-${base}`;
};

export {
  getControlId,
  getControlSetterButtonId
};
