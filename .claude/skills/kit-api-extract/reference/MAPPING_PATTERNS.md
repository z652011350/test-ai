# NAPI/ANI 映射模式知识库

本文件记录 HarmonyOS/OpenHarmony 中 JS API 到 C++ 实现的各种映射模式。
每次使用 kit-api-extract skill 后，若发现新模式，应追加到此文件。

---

### 模式1：DECLARE_NAPI_FUNCTION 宏注册

**描述**：最传统的 NAPI 函数注册方式，通过宏将 JS 方法名映射到 C++ 函数。通常出现在 `napi_property_descriptor` 数组中。

**正则表达式**：`DECLARE_NAPI_FUNCTION\s*\(\s*"([^"]+)"\s*,\s*(\w+)`

**代码结构**：
```cpp
napi_property_descriptor properties[] = {
    DECLARE_NAPI_FUNCTION("getWant", NAPI_PAGetWant),
    DECLARE_NAPI_FUNCTION("startAbility", NAPI_PAStartAbility),
    DECLARE_NAPI_FUNCTION("getBundleInfo", GetBundleInfo),
};
```

**关键文件位置**：`frameworks/js/napi/<module>/` 或 `interfaces/kits/napi/src/`

---

### 模式2：napi_create_function 动态注册

**描述**：通过 `napi_create_function` 动态创建 NAPI 函数并挂载到 exports 对象，不使用宏。

**正则表达式**：`napi_create_function\s*\(\s*(?:env|Env)\s*,\s*"([^"]+)"\s*,\s*[^,]+,\s*(\w+)`

**代码结构**：
```cpp
NAPI_CALL(env, napi_create_function(env, "isCanceled", NAPI_AUTO_LENGTH, Task::IsCanceled, NULL, &isCanceledFunc));
NAPI_CALL(env, napi_set_named_property(env, exports, "isCanceled", isCanceledFunc));
```

**关键文件位置**：`frameworks/js/napi/` 下各子模块

---

### 模式3：nm_modname 模块名注册

**描述**：NAPI 模块通过 `.nm_modname` 字段注册模块名，将 JS 的 `@ohos.xxx.yyy` 映射到具体代码仓。通常出现在 `native_module.cpp` 或 `*_module.cpp` 中。

**正则表达式**：`\.nm_modname\s*=\s*"([^"]+)"`

**代码结构**：
```cpp
static napi_module _module = {
    .nm_version = 1,
    .nm_flags = 0,
    .nm_filename = nullptr,
    .nm_modname = "ability.featureAbility",
    .nm_register_func = FeatureAbilityInit,
    ...
};
```

**用途**：用于模块→代码仓映射（Phase 2 map 阶段）

---

### 模式4：napi_define_class 类注册

**描述**：通过 `napi_define_class` 注册 JS 类，类的方法在 `napi_property_descriptor` 中声明。常见于面向对象的 API（如 DeviceManager、AVPlayer）。

**正则表达式**：`napi_define_class\s*\([^;]+Constructor`

**代码结构**：
```cpp
napi_property_descriptor desc[] = {
    DECLARE_NAPI_FUNCTION("getDeviceName", GetDeviceName),
    DECLARE_NAPI_FUNCTION("authenticateDevice", AuthenticateDevice),
};
NAPI_CALL(env, napi_define_class(env, "DeviceManager", NAPI_AUTO_LENGTH, Constructor, nullptr,
    sizeof(desc) / sizeof(desc[0]), desc, nullptr, &result));
```

**关键文件位置**：`interfaces/kits/js/` 或 `interfaces/kits/js4.0/`

---

### 模式5：napi_define_properties 批量导出

**描述**：通过 `napi_define_properties` 将一组 NAPI 属性/方法批量绑定到 exports 对象。常与 `DECLARE_NAPI_FUNCTION` 或 `DECLARE_NAPI_GETTER` 配合使用。

**正则表达式**：`napi_define_properties\s*\(`

**代码结构**：
```cpp
napi_property_descriptor desc[] = {
    DECLARE_NAPI_FUNCTION("function1", Func1),
    DECLARE_NAPI_FUNCTION("function2", Func2),
};
napi_define_properties(env, exports, sizeof(desc) / sizeof(desc[0]), desc);
```

**关键文件位置**：`frameworks/js/napi/` 下各子模块

---

### 模式6：on/off 事件分发模式

**描述**：多个 JS API（如 onAdd/offAdd/onUpdate 等）并非独立注册的 NAPI 函数，而是通过通用的 `on(type, callback)` / `off(type, callback?)` 入口分发。`type` 参数区分不同事件类型，内部维护独立的 listener 列表。

**正则表达式**：`DECLARE_NAPI_FUNCTION\s*\(\s*"(on|off)"\s*,\s*(Register|Unregister)\)`

**代码结构**：
```cpp
napi_property_descriptor properties[] = {
    DECLARE_NAPI_FUNCTION("on", Register),
    DECLARE_NAPI_FUNCTION("off", Unregister),
};

napi_value Register(napi_env env, napi_callback_info info) {
    // 解析 type 参数
    if (type == "add") { addListeners.push_back(callback); }
    else if (type == "update") { updateListeners.push_back(callback); }
    else if (type == "remove") { removeListeners.push_back(callback); }
}
```

**JS API 到 C++ 的映射**：
- `onAdd(cb)` → `on("add", cb)` → `Register` (type="add")
- `offAdd(cb)` → `off("add", cb)` → `Unregister` (type="add")

**关键文件位置**：`interfaces/kits/js/bundle_monitor/` 等事件监听模块

---

### 模式7：BindNativeFunction / BindNativeFunctionInObj（OHOS 特有封装）

**描述**：OHOS 提供的 `BindNativeFunction` 和 `BindNativeFunctionInObj` 辅助函数，封装了 `napi_define_properties` 调用。不使用 DECLARE_NAPI_FUNCTION 宏。

**正则表达式**：`BindNativeFunction\s*\(\s*(?:env|context)\s*,\s*(?:exports|obj)\s*,\s*"([^"]+)"\s*,\s*(\w+)`

**代码结构**：
```cpp
BindNativeFunction(env, exports, "register", JsContinuationManager::Register);
BindNativeFunction(env, exports, "unregister", JsContinuationManager::Unregister);
```

**关键文件位置**：`interfaces/kits/napi/` 或 `frameworks/js/napi/` 下各模块

---

### 模式8：纯 JS/ABC 模块（无 C++ nm_register_func）

**描述**：部分模块（如 InsightIntentExecutor、ApplicationStateChangeCallback）是纯 JS/ArkTS 类，通过嵌入的 .js 或 .abc 字节码注册，没有 C++ 的 nm_register_func。其方法在 JS 层定义，C++ 侧通过函数名字符串反射调用。

**识别特征**：
- `native_module.cpp` 中无 `nm_register_func` 或使用空/默认注册
- 模块目录下有 `.js` 文件
- C++ 侧有 `JsXxx` 类通过 `JS_FUNC_NAME` 数组按名称调用 JS 方法

**代码结构**：
```cpp
// native_module.cpp - 无 nm_register_func
static napi_module _module = {
    .nm_modname = "app.ability.InsightIntentExecutor",
    // 无 nm_register_func - 纯 JS 模块
};

// C++ 侧通过函数名调用 JS 方法
const std::vector<std::string> JS_FUNC_NAME_FOR_MODE = {
    "onExecuteInUIAbilityForegroundMode",
    "onExecuteInUIAbilityBackgroundMode",
    ...
};
```

**关键文件位置**：`frameworks/js/napi/insight_intent/` 等生命周期回调模块

### 模式9：CallObjectMethod 生命周期回调（反射调用 JS 方法）

**描述**：生命周期回调 API（如 onAcceptWant、onNewProcessRequest、onAuth 等）不在 C++ 侧通过 NAPI 宏注册。相反，C++ 通过 `napi_get_named_property` + `napi_call_function` 或 `CallObjectMethod` 按方法名字符串反射调用 ETS/JS 层的回调函数。模块通常为纯 JS/ABC 模块（无 nm_register_func）。

**正则表达式**：`CallObjectMethod\s*\(\s*"(on\w+)"` 或 `napi_get_named_property\s*\([^,]+,\s*\w+,\s*"(on\w+)"`

**代码结构**：
```cpp
// C++ 侧通过名字字符串调用 JS 方法
napi_value method = nullptr;
napi_get_named_property(env, obj, "onAcceptWant", &method);
napi_call_function(env, obj, method, argc, argv, &result);

// 或使用封装的 CallObjectMethod
auto result = CallObjectMethod("onAuth", argv, ARGC_TWO);
```

**JS API 到 C++ 的映射**：
- `onAcceptWant(want)` → C++ `CallAcceptOrRequestSync("onAcceptWant")` → `js_ability_stage.cpp`
- `onAuth(proxy, data)` → C++ `CallObjectMethod("onAuth")` → `js_agent_extension.cpp`

**关键文件位置**：`frameworks/native/appkit/` 和 `frameworks/js/napi/app/` 下的生命周期模块

---

### 模式10：ETS+ANI 绑定（ani_native_function）

**描述**：部分新模块（如 autoStartupManager、abilityManager 的事件监听）使用 ETS+ANI 双层架构。模块既有 NAPI 层（通过 BindNativeFunction 注册 on/off 通用入口），也有 ANI/ETS 层通过 `ani_native_function` 注册。运行时根据 VM 类型选择 NAPI 或 ANI 实现。

**正则表达式**：`ani_native_function\s*\(`

**代码结构**：
```cpp
// NAPI 层（兼容模式）
BindNativeFunction(env, exportObj, "on", JsAutoStartupManager::On);

// ANI 层（新架构）
ani_native_function aniFunc = {
    .name = "on",
    .func = reinterpret_cast<void*>(JsAutoStartupManager::On),
};
```

**关键文件位置**：`frameworks/js/napi/ability_auto_startup_manager/`、`frameworks/js/napi/ability_manager/`

---

### 模式11：Taihe IDL 绑定模式

**描述**：通过 `.taihe` IDL 文件定义接口，由 Taihe 框架自动生成绑定代码。使用 `TH_EXPORT_CPP_API_xxx` 宏导出实现函数。不使用传统 NAPI 注册机制。

**正则表达式**：`TH_EXPORT_CPP_API_\w+` 或 `.taihe` 文件中的 `interface` 定义

**代码结构**：
```taihe
// ohos.app.ability.continueManager.taihe
interface ContinueManager {
    void onPrepareContinue(Context context, AsyncCallback<ContinueResultInfo> callback);
    void offPrepareContinue(Context context, AsyncCallback<ContinueResultInfo>? callback);
}
```

```cpp
// 实现文件 ohos.app.ability.continueManager.impl.cpp
TH_EXPORT_CPP_API_OnPrepareContinueInner(params) {
    // 实现代码
    AniContinueManager::OnContinueStateCallback(...);
}
```

**关键文件位置**：`interfaces/taihe/` 目录下的 `.taihe` 文件和 `src/` 下的 `.impl.cpp` 文件

---

### 模式12：纯 JS 实现模块（NAPI 模块 + JS 门面）

**描述**：部分模块（如 dataUriUtils、sendableContextManager）在 NAPI 层注册了模块入口（有 nm_modname），但具体的 API 实现在 .js 文件中。JS 文件作为门面，部分方法直接用 JS 实现（纯字符串操作等），部分通过 `requireInternal` 调用底层 C++ 实现。

**正则表达式**：`.js` 文件中直接定义函数，或 `requireInternal` 调用

**代码结构**：
```javascript
// ability_data_uri_utils.js — 纯 JS 实现
function attachId(uri, id) {
    return uri + '/' + id;
}

// sendable_context_manager.js — 混合模式
const internal = requireInternal('sendable_context_manager');
function convertFromContext(context) {
    return internal.convertFromContext(context);
}
```

**关键文件位置**：`frameworks/js/napi/` 下各模块中的 `.js` 文件

---

### 模式13：双层 __context_impl__ 注入模式

**描述**：某些纯 JS/ABC 模块（如 InsightIntentContext）在 JS 层定义接口，但实际 C++ 实现对象通过 `__context_impl__` 属性由框架内部注入。JS 层通过 `this.__context_impl__.methodName()` 调用 C++ 实现，C++ 侧通过 `BindNativeFunction` 在注入的对象上注册方法。

**正则表达式**：`__context_impl__\.`

**代码结构**：
```javascript
// insight_intent_context.js
class InsightIntentContext {
    setReturnModeForUIAbilityForeground(returnMode) {
        this.__context_impl__.setReturnModeForUIAbilityForeground(returnMode);
    }
}
```

**关键文件位置**：`frameworks/js/napi/insight_intent_context/` 等 Context 类模块


### 模式14：JSI NativeModule Bridge（ArkUI 组件属性绑定）

**描述**：ArkUI 组件的属性 API（如 width、height、onClick 等）不通过传统 NAPI 的 nm_modname 注册，而是通过 JSI (JS Interface) 层的 `arkts_native_*_bridge.cpp` 文件进行绑定。每个组件有对应的 bridge 文件和 modifier 文件。

**正则表达式**：`arkts_native_(\w+)_bridge\.cpp`

**代码结构**：
```cpp
// arkts_native_text_bridge.cpp — JSI 绑定入口
ArkUI_NativeModuleAPI* module = GetArkUINodeModifiers();
module->textModifier->setTextFont(node, value);
```

**映射链路**：
```
.d.ts 声明 → arkts_native_*_bridge.cpp (JSI绑定)
          → node_*_modifier.h/cpp (Framework声明+实现)
          → frameworks/core/components_ng/pattern/*/ (业务逻辑)
```

**关键文件位置**：
- Bridge: `arkui_ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/nativeModule/`
- Modifier: `arkui_ace_engine/frameworks/core/interfaces/native/node/`

---

### 模式15：UIContext JS Bridge（requireNapi 加载模式）

**描述**：`@ohos.arkui.UIContext` 是一个 JS 桥接类，通过 `globalThis.requireNapi('xxx')` 加载底层 NAPI 模块。

**正则表达式**：`globalThis\.requireNapi\(['"]([^'"]+)['"]\)`

**代码结构**：
```javascript
class Font {
    constructor(instanceId) {
        this.ohos_font = globalThis.requireNapi('font');
    }
    registerFont(options) {
        __JSScopeUtil__.syncInstanceId(this.instanceId_);
        this.ohos_font.registerFont(options);
    }
}
```

**关键文件位置**：`arkui_ace_engine/frameworks/bridge/declarative_frontend/engine/jsUIContext.js`

---

### 模式16：ANI 双层绑定（window_window_manager 模式）

**描述**：window_window_manager 仓库中的 display、screen、PiPWindow 模块使用 ANI 而非传统 NAPI 进行绑定。

**正则表达式**：`ANI_Constructor\s*\(|Namespace_BindNativeFunctions\s*\(`

**关键文件位置**：`window_window_manager/interfaces/kits/ani/`


---

发现新模式时，按以下格式追加：

```markdown
### 模式N：{模式名称}

**描述**：{简要描述映射机制}

**正则表达式**：{可用于 grep/搜索的正则}

**代码结构**：
```cpp
{示例代码}
```

**关键文件位置**：{通常出现的目录路径模式}
```