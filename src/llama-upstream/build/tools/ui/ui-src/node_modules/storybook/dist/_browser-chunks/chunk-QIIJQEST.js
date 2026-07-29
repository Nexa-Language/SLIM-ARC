import {
  StatusTypeIdMismatchError
} from "./chunk-C3TKC4WX.js";
import {
  StatusTypeIdMismatchError as StatusTypeIdMismatchError2
} from "./chunk-MFQQ5L5I.js";
import {
  StorybookError
} from "./chunk-2HVKLHKJ.js";
import {
  require_picocolors_browser
} from "./chunk-7YGTGCDG.js";
import {
  __toESM
} from "./chunk-A242L54C.js";

// src/server-errors.ts
var import_picocolors = __toESM(require_picocolors_browser(), 1);
var StatusTypeIdMismatchError3 = class extends StorybookError {
  constructor(data) {
    super({
      name: "StatusTypeIdMismatchError",
      category: "CORE-SERVER" /* CORE_SERVER */,
      code: 16,
      message: `Status has typeId "${data.status.typeId}" but was added to store with typeId "${data.typeId}". Full status: ${JSON.stringify(
        data.status,
        null,
        2
      )}`
    });
    this.data = data;
  }
};

// src/shared/status-store/index.ts
var STATUS_VALUE_PREFIX = "status-value:", STATUS_VALUES = [
  "status-value:pending",
  "status-value:success",
  "status-value:new",
  "status-value:modified",
  "status-value:affected",
  "status-value:warning",
  "status-value:error",
  "status-value:unknown"
], toStatusValue = (shortName) => {
  if (shortName === "related") return "status-value:affected";
  let candidate = `${STATUS_VALUE_PREFIX}${shortName}`;
  return STATUS_VALUES.includes(candidate) ? candidate : void 0;
}, statusValueShortName = (value) => value === "status-value:affected" ? "related" : value.slice(STATUS_VALUE_PREFIX.length);
var CHANGE_DETECTION_STATUS_TYPE_ID = "storybook/change-detection", UNIVERSAL_STATUS_STORE_OPTIONS = {
  id: "storybook/status",
  leader: !0,
  initialState: {}
}, StatusStoreEventType = {
  SELECT: "select"
};
function countStatusesByValue(allStatuses) {
  let counts = {};
  for (let statusByTypeId of Object.values(allStatuses))
    for (let status of Object.values(statusByTypeId))
      counts[status.value] = (counts[status.value] ?? 0) + 1;
  return counts;
}
function createStatusStore({
  universalStatusStore,
  useUniversalStore,
  environment
}) {
  let fullStatusStore = {
    getAll() {
      return universalStatusStore.getState();
    },
    set(statuses) {
      universalStatusStore.setState((state) => {
        let newState = { ...state };
        for (let status of statuses) {
          let { storyId, typeId } = status;
          newState[storyId] = { ...newState[storyId] ?? {}, [typeId]: status };
        }
        return newState;
      });
    },
    onAllStatusChange(listener) {
      return universalStatusStore.onStateChange((state, prevState) => {
        listener(state, prevState);
      });
    },
    onSelect(listener) {
      return universalStatusStore.subscribe(StatusStoreEventType.SELECT, (event) => {
        listener(event.payload);
      });
    },
    selectStatuses: (statuses) => {
      universalStatusStore.send({ type: StatusStoreEventType.SELECT, payload: statuses });
    },
    unset(storyIds) {
      if (!storyIds) {
        universalStatusStore.setState({});
        return;
      }
      universalStatusStore.setState((state) => {
        let newState = { ...state };
        for (let storyId of storyIds)
          delete newState[storyId];
        return newState;
      });
    },
    typeId: void 0
  }, getStatusStoreByTypeId = (typeId) => ({
    getAll: fullStatusStore.getAll,
    set(statuses) {
      universalStatusStore.setState((state) => {
        let newState = { ...state };
        for (let status of statuses) {
          let { storyId } = status;
          if (status.typeId !== typeId)
            switch (environment) {
              case "server":
                throw new StatusTypeIdMismatchError3({
                  status,
                  typeId
                });
              case "manager":
                throw new StatusTypeIdMismatchError({
                  status,
                  typeId
                });
              case "preview":
              default:
                throw new StatusTypeIdMismatchError2({
                  status,
                  typeId
                });
            }
          newState[storyId] = { ...newState[storyId] ?? {}, [typeId]: status };
        }
        return newState;
      });
    },
    onAllStatusChange: fullStatusStore.onAllStatusChange,
    onSelect(listener) {
      return universalStatusStore.subscribe(StatusStoreEventType.SELECT, (event) => {
        event.payload.some((status) => status.typeId === typeId) && listener(event.payload);
      });
    },
    unset(storyIds) {
      universalStatusStore.setState((state) => {
        let newState = { ...state };
        for (let storyId in newState)
          if (newState[storyId]?.[typeId] && (!storyIds || storyIds?.includes(storyId))) {
            let { [typeId]: omittedStatus, ...storyStatusesWithoutTypeId } = newState[storyId];
            newState[storyId] = storyStatusesWithoutTypeId;
          }
        return newState;
      });
    },
    typeId
  });
  return useUniversalStore ? {
    getStatusStoreByTypeId,
    fullStatusStore,
    universalStatusStore,
    useStatusStore: (selector) => useUniversalStore(universalStatusStore, selector)[0]
  } : { getStatusStoreByTypeId, fullStatusStore, universalStatusStore };
}

export {
  toStatusValue,
  statusValueShortName,
  CHANGE_DETECTION_STATUS_TYPE_ID,
  UNIVERSAL_STATUS_STORE_OPTIONS,
  countStatusesByValue,
  createStatusStore
};
