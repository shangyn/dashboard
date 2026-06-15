# 企业后台管理系统 — 设计文档

**日期**: 2026-06-15
**状态**: 设计阶段

---

## 一、项目概述

企业级内部后台管理系统，运行于局域网。实现用户管理、角色权限控制、动态模块展示、文件上传管理。

**核心设计理念**：
- 管理员（`role.is_admin = true`）：侧边栏布局，管理用户/角色/模块/上传配置
- 普通角色（`role.is_admin = false`）：无侧边栏，模块卡片网格 + 用户控制台（上传）

---

## 二、视觉风格

- **登录页**：蓝色渐变背景 + 居中白色卡片，简约商务风
- **管理员页**：左侧深色侧边栏 + 白色顶栏 + 灰色内容区
- **普通用户页**：仅白色顶栏（系统控制台 + 用户信息 + 用户控制台按钮），内容区为模块卡片网格（3列）
- **上传页**：左侧菜单导航 + 右侧拖拽上传区 + 底部统计
- **主题色**：蓝色系（`#1a73e8` / `#0d47a1`）

---

## 三、数据库设计（5张表）

### 3.1 user 用户表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 用户ID |
| username | String(80) | UNIQUE, NOT NULL | 工号，登录账号 |
| password | String(200) | NOT NULL | bcrypt 哈希密码 |
| real_name | String(50) | | 真实姓名 |
| role_id | Integer | FK → role.id | 所属角色 |
| is_active | Boolean | 默认 True | 是否启用 |
| created_at | DateTime | 默认 now | 创建时间 |

### 3.2 role 角色表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 角色ID |
| role_name | String(50) | UNIQUE, NOT NULL | 角色名称 |
| is_admin | Boolean | 默认 False | 是否为管理员角色 |
| permissions | Text | | JSON数组，权限标识列表 |
| created_at | DateTime | 默认 now | 创建时间 |

**permissions 示例**：
- 管理员：`["user_manage", "role_manage", "module_manage", "upload_manage", "dashboard_receivables", "dashboard_performance", "upload_performance", "upload_payment", ...]`
- 报价员：`["dashboard_receivables", "upload_performance"]`

### 3.3 module 模块表（看板入口）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 模块ID |
| name | String(100) | NOT NULL | 看板名称 |
| description | Text | | 描述文字 |
| permission | String(50) | NOT NULL | 对应权限标识 |
| url | String(200) | | dashboard HTML 路径 |
| icon | String(50) | | 可选图标名 |
| sort_order | Integer | 默认 0 | 排序 |
| is_active | Boolean | 默认 True | 是否启用 |

**权限标识（permission）是 module 和 role.permissions 的关联桥梁**。用户的 role.permissions 中包含 module.permission 时，该模块卡片对该用户可见。

### 3.4 upload_config 上传配置表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 配置ID |
| name | String(100) | NOT NULL | 上传项名称 |
| description | Text | | 描述说明 |
| code | String(50) | UNIQUE, NOT NULL | 唯一标识符，对应后端处理函数名 |
| permission | String(50) | NOT NULL | 所需权限标识 |
| file_types | String(100) | | 允许的文件类型，如 `.xlsx,.xls,.csv` |
| required_columns | Text | | 必需列说明（可选，展示用） |
| sort_order | Integer | 默认 0 | 排序 |
| is_active | Boolean | 默认 True | 是否启用 |

**code 字段的设计目的**：
- 管理员创建上传类型时指定 code
- 后端维护一个 `code → handler` 映射表
- 文件上传后根据 code 查找对应解析函数
- 若 code 尚无 handler → 文件仅存储不解析，系统不会崩溃
- 新增上传类型 → 管理员加记录 + 开发者加 handler，互不影响

### 3.5 file_upload 上传记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, auto | 记录ID |
| filename | String(200) | | 原始文件名 |
| stored_path | String(300) | | 服务器存储路径 |
| file_size | Integer | | 文件大小（字节） |
| upload_config_id | Integer | FK → upload_config.id | 对应上传配置 |
| user_id | Integer | FK → user.id | 上传者 |
| status | String(20) | 默认 'stored' | stored / parsed / error |
| message | Text | | 处理结果说明 |
| uploaded_at | DateTime | 默认 now | 上传时间 |

---

## 四、预定义权限标识清单

### 管理类权限（控制管理员侧边栏菜单项）
- `dashboard` — 首页看板（所有人默认拥有）
- `user_manage` — 用户管理页面
- `role_manage` — 角色管理页面
- `module_manage` — 模块管理页面
- `upload_manage` — 上传配置管理页面

### 看板类权限（控制模块卡片可见性）
- `dashboard_receivables` — 报价统计分析看板
- `dashboard_performance` — 业绩完成情况看板
- `dashboard_daily` — 国际运营业绩日报看板
- `dashboard_ledger` — 报价执行台账看板
- `dashboard_function` — 职能工作看板
- `dashboard_spare_parts` — 国贸备件报价

### 上传类权限（控制上传功能可见性）
- `upload_performance` — 业绩数据上传
- `upload_module_target` — 模块业绩指标上传
- `upload_payment` — 回款数据上传
- `upload_spare_parts` — 商贸备件数据上传
- `upload_trade` — 商贸数据上传
- `upload_delivery` — 备件发货数据上传
- `upload_offline_quote` — 2026年线下报价数据上传

---

## 五、后端 API 设计

**统一规范**：
- 前缀：`/api`
- 除 `/api/login` 外均需 `Authorization: Bearer <token>` 头
- 统一返回格式：`{ "code": 200, "msg": "success", "data": ... }`
- 权限不足返回：`{ "code": 403, "msg": "无权限", "data": null }`

### 5.1 认证

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/api/login` | 登录，返回 token + 用户信息（含 role 含 permissions） | 无 |
| GET | `/api/current-user` | 获取当前登录用户完整信息 | 登录即可 |
| PUT | `/api/change-password` | 修改自己的密码（旧密码 + 新密码） | 登录即可 |

**POST /api/login 返回格式**：
```json
{
  "code": 200,
  "data": {
    "token": "eyJ...",
    "user": {
      "id": 1,
      "username": "admin",
      "real_name": "管理员",
      "role": {
        "id": 1,
        "role_name": "管理员",
        "is_admin": true,
        "permissions": ["user_manage", "role_manage", ...]
      }
    }
  }
}
```

### 5.2 用户管理（需 `user_manage` 权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/users` | 分页查询，支持 username/real_name 模糊搜索 |
| POST | `/api/users` | 新增用户 |
| PUT | `/api/users/<id>` | 修改用户（real_name, role_id, is_active） |
| DELETE | `/api/users/<id>` | 删除用户（物理删除） |
| PUT | `/api/users/<id>/reset-password` | 重置密码为默认值 `123456` |

**GET 查询参数**：`?page=1&page_size=10&username=xxx&real_name=xxx`

### 5.3 角色管理（需 `role_manage` 权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/roles` | 查询所有角色（用于下拉选择） |
| POST | `/api/roles` | 新增角色 |
| PUT | `/api/roles/<id>` | 修改角色（名称、is_admin、permissions） |
| DELETE | `/api/roles/<id>` | 删除角色（有关联用户时禁止并返回提示） |

### 5.4 模块管理（需 `module_manage` 权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/modules` | 查询所有模块 |
| POST | `/api/modules` | 新增模块 |
| PUT | `/api/modules/<id>` | 修改模块 |
| DELETE | `/api/modules/<id>` | 删除模块 |

### 5.5 上传配置管理（需 `upload_manage` 权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/upload-configs` | 查询所有上传配置 |
| POST | `/api/upload-configs` | 新增上传配置 |
| PUT | `/api/upload-configs/<id>` | 修改上传配置 |
| DELETE | `/api/upload-configs/<id>` | 删除上传配置 |

### 5.6 文件上传（需对应 upload_xxx 权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload/<code>` | 上传文件（根据 code 匹配 upload_config） |
| GET | `/api/upload-history` | 查询当前用户的上传记录 |
| GET | `/api/upload-stats` | 获取统计数据：上传次数、更新次数、数据库大小 |

### 5.7 权限查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/my-modules` | 当前用户可见的模块列表（根据 permissions 过滤） |
| GET | `/api/my-upload-configs` | 当前用户可用的上传配置列表 |

### 5.8 权限装饰器

```python
def permission_required(permission):
    """检查当前用户是否拥有指定权限"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_jwt_identity()
            if permission not in user.get('permissions', []):
                return jsonify(code=403, msg='无权限'), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
```

---

## 六、前端架构

### 6.1 目录结构

```
frontend/
├── index.html
├── vite.config.js
├── package.json
├── src/
│   ├── main.js              # 入口，注册路由/Pinia/ElementPlus
│   ├── App.vue               # 根组件
│   ├── api/
│   │   ├── request.js        # Axios 实例（拦截器：自动加token、统一错误处理）
│   │   ├── auth.js           # 登录/logout/当前用户
│   │   ├── users.js          # 用户CRUD
│   │   ├── roles.js          # 角色CRUD
│   │   ├── modules.js        # 模块CRUD + my-modules
│   │   ├── upload-config.js  # 上传配置CRUD + my-upload-configs
│   │   └── upload.js         # 文件上传 + 上传历史 + 统计
│   ├── stores/
│   │   ├── auth.js           # Pinia: token, userInfo, permissions
│   │   └── app.js            # Pinia: sidebar状态、全局loading
│   ├── router/
│   │   └── index.js          # 路由定义 + beforeEach守卫
│   ├── layouts/
│   │   ├── AdminLayout.vue   # 侧边栏 + 顶栏 + router-view
│   │   └── UserLayout.vue    # 仅顶栏 + router-view
│   ├── views/
│   │   ├── Login.vue         # 登录页
│   │   ├── Home.vue          # 普通用户：模块卡片选择页
│   │   ├── Dashboard.vue     # iframe 看板页
│   │   ├── UploadConsole.vue # 用户控制台（上传页）
│   │   ├── SystemInfo.vue    # 无上传权限时显示的系统信息
│   │   ├── admin/
│   │   │   ├── AdminDashboard.vue  # 管理员首页
│   │   │   ├── UserManage.vue      # 用户管理
│   │   │   ├── RoleManage.vue      # 角色管理
│   │   │   ├── ModuleManage.vue    # 模块管理
│   │   │   └── UploadConfigManage.vue # 上传配置管理
│   │   └── common/
│   │       └── 403.vue       # 无权限页
│   └── components/
│       └── UploadZone.vue    # 可复用的拖拽上传组件
```

### 6.2 路由设计

```javascript
const routes = [
  { path: '/login', component: Login },

  // 管理员路由（AdminLayout + 需 is_admin）
  {
    path: '/admin',
    component: AdminLayout,
    meta: { requireAdmin: true },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      { path: 'dashboard', component: AdminDashboard },
      { path: 'user-manage', component: UserManage },
      { path: 'role-manage', component: RoleManage },
      { path: 'module-manage', component: ModuleManage },
      { path: 'upload-config-manage', component: UploadConfigManage },
    ]
  },

  // 普通用户路由（UserLayout + 登录即可）
  {
    path: '/',
    component: UserLayout,
    meta: { requireAuth: true },
    children: [
      { path: '', redirect: '/home' },
      { path: 'home', component: Home },
      { path: 'dashboard/:id', component: Dashboard, props: true },
      { path: 'upload-console', component: UploadConsole },
      { path: 'upload-console/:code', component: UploadConsole },
    ]
  },

  { path: '/403', component: Forbidden },
  { path: '/:pathMatch(.*)*', redirect: '/home' },
]
```

### 6.3 路由守卫逻辑

```
router.beforeEach:
  1. 无 token → 跳转 /login
  2. 有 token 但无 userInfo → 调 /api/current-user 获取
  3. 目标路由 requireAdmin → 检查 user.role.is_admin
     - 不是 → 跳转 /403
  4. 用户已是管理员但访问 / → 重定向到 /admin/dashboard
```

### 6.4 布局切换逻辑

- `role.is_admin === true` → 使用 `AdminLayout`（侧边栏 + 顶栏 + 内容区）
- `role.is_admin === false` → 使用 `UserLayout`（顶栏 + 内容区，无侧边栏）

### 6.5 关键页面说明

#### Login.vue
- 蓝色渐变背景全屏
- 居中白色圆角卡片
- 工号输入框 + 密码输入框
- "记住密码"复选框（localStorage）
- "登录"按钮
- 登录成功 → 存储 token/userInfo 到 Pinia → 跳转

#### Home.vue（模块卡片选择页）
- 顶栏：系统控制台 | 用户信息/头像下拉 | 用户控制台按钮
- 欢迎区："欢迎回来，{real_name}" + "请选择您要查看的看板"
- 统计行：可用看板数 | 监控指标数 | 数据维度数
- 模块卡片网格（3列）：标题 + 描述 + "查看看板"按钮
- 调用 `/api/my-modules` 获取当前用户可见模块

#### Dashboard.vue（iframe 看板页）
- 通过路由参数 `id` 获取 module 信息
- `<iframe>` 加载 Flask 托管的 dashboard HTML
- 顶部有返回按钮和看板标题

#### UploadConsole.vue（用户控制台）
- 左侧菜单导航（数据管理 / 系统信息）
- 点击"数据管理"展开上传类型列表
- 每个上传类型显示拖拽上传区
- 底部统计行：上传次数 | 更新次数 | 数据库大小
- 若用户无任何上传权限 → 显示 SystemInfo 内容

### 6.6 状态管理（Pinia）

**auth store**：
- `token` — JWT 字符串
- `userInfo` — 当前用户信息（含 role 含 permissions）
- `isAdmin` — 计算属性，`userInfo.role.is_admin`
- `permissions` — 计算属性，`userInfo.role.permissions`
- `login()` / `logout()` / `fetchCurrentUser()` actions

---

## 七、后端目录结构

```
backend/
├── app.py                 # Flask 应用入口，注册蓝图，初始化数据库
├── config.py              # 配置（数据库路径、JWT密钥、上传目录等）
├── models.py              # 所有 SQLAlchemy 模型
├── auth.py                # 认证相关蓝图
├── users.py               # 用户管理蓝图
├── roles.py               # 角色管理蓝图
├── modules.py             # 模块管理蓝图
├── upload_config.py       # 上传配置管理蓝图
├── upload.py              # 文件上传处理蓝图
├── decorators.py          # 权限装饰器
├── seed.py                # 初始数据（首次运行自动创建管理员账号）
├── uploads/               # 上传文件存储目录（自动创建）
└── instance/
    └── system.db          # SQLite 数据库文件（自动生成）
```

---

## 八、初始数据

系统首次启动时自动执行 seed：

```python
def seed():
    if Role.query.count() == 0:
        admin_role = Role(
            role_name='管理员',
            is_admin=True,
            permissions=json.dumps([
                'dashboard',
                'user_manage', 'role_manage', 'module_manage', 'upload_manage',
                'dashboard_receivables', 'dashboard_performance',
                'upload_performance', 'upload_payment'
            ])
        )
        db.session.add(admin_role)
        db.session.flush()

        admin_user = User(
            username='admin',
            password=bcrypt.generate_password_hash('admin123').decode('utf-8'),
            real_name='管理员',
            role_id=admin_role.id,
            is_active=True
        )
        db.session.add(admin_user)
        db.session.commit()
```

---

## 九、文件上传处理流程

**核心规则：每次上传默认覆盖数据库中的对应数据，而非追加。**

```
POST /api/upload/<code>
  ↓
1. 根据 code 查找 upload_config → 不存在返回404
2. 检查用户权限（role.permissions 包含 upload_config.permission）→ 无权限返回403
3. 保存原始文件到 backend/uploads/{code}/{timestamp}_{filename}（留底）
4. 在 file_upload 表创建记录（status='uploading'）
5. 查找后端 handler 映射表：
   - 存在对应 handler → 调用解析函数（先清空目标表数据，再写入新数据）
     → 成功：更新 status='parsed'，记录解析行数
     → 失败：更新 status='error'，记录错误信息，数据库数据回滚（保留旧数据）
   - 不存在 handler → 更新 status='stored'，message='暂不支持解析，文件已保存'
6. 返回上传结果
7. 更新统计数据：上传次数+1，更新次数+N（N=解析影响的行数），数据库大小
```

**覆盖逻辑说明**：
- 每次上传解析成功后，**先删除该 code 对应的目标数据表中的全部记录**，再批量插入新解析的数据
- 整个过程在同一个数据库事务中：解析失败则自动回滚，旧数据不丢失
- 原始文件始终保留在 `uploads/` 目录下，可追溯

**handler 映射机制**（`upload/handlers.py`）：
```python
# 每个解析函数签名：def handler(file_path: str) -> dict
# 返回 { "success": True/False, "message": "...", "rows": 0 }
# handler 内部负责：清空目标表 → 解析文件 → 批量插入 → 提交事务

HANDLERS = {
    "performance_data": parse_performance_excel,   # 已有
    "payment_data":      parse_payment_excel,       # 后续添加
    # 新增 code 只需在此加一行映射 + 实现函数
}
```

---

## 十、部署方案

- **开发环境**：Flask 监听 `0.0.0.0:5000`，Vite dev server 通过 `--host` 暴露，前端代理 API 到 Flask
- **生产环境**：`npm run build` 生成 dist，Flask 直接托管静态文件 + API
- **数据库**：`backend/instance/system.db`，SQLite 单文件，局域网内直接读写
- **上传文件**：`backend/uploads/` 目录，按 code 分子目录存储

---

## 十一、开发阶段

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **Phase 1** | 后端：项目骨架、models、seed、auth API | 无 |
| **Phase 2** | 后端：用户管理、角色管理、模块管理、上传配置 CRUD API | Phase 1 |
| **Phase 3** | 后端：文件上传 API、权限查询 API | Phase 2 |
| **Phase 4** | 前端：项目骨架、Login、路由守卫、Pinia store | Phase 1 |
| **Phase 5** | 前端：AdminLayout + 用户管理/角色管理/模块管理/上传配置页面 | Phase 2+4 |
| **Phase 6** | 前端：UserLayout + Home模块卡片 + Dashboard iframe + UploadConsole | Phase 3+4 |

---

## 十二、待后续实现

- Dashboard HTML 生成脚本集成（现有 `main_dashboard.py` 的输出接入系统）
- 其他看板页面的开发
- Excel 解析 handler 的具体业务逻辑
- 数据看板统计的真实数值
