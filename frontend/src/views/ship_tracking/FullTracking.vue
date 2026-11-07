<template>
  <div class="st-page" v-loading="loading">
    <div class="st-hero">
      <div class="st-hero-main">
        <h2 class="st-title">发货梯号明细</h2>
        <div class="st-subtitle">
          <span>全量计划、实际发货与订舱状态</span>
          <el-tag size="small" effect="plain" type="info">{{ context.role_name }}</el-tag>
        </div>
      </div>
      <div class="st-hero-actions">
        <el-button size="small" @click="loadData">刷新</el-button>
        <el-button size="small" type="success" plain @click="handleExport">下载明细 Excel</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="st-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="全量明细" name="tracking">
        <div class="st-filter-panel">
          <el-select v-model="filters.month" size="small" clearable placeholder="全部月份" style="width: 104px">
            <el-option v-for="month in months" :key="month" :label="month" :value="month" />
          </el-select>
          <el-select v-model="filters.region" size="small" clearable placeholder="全部大区" style="width: 104px">
            <el-option label="大区1" value="大区1" />
            <el-option label="大区2" value="大区2" />
          </el-select>
          <el-select v-model="filters.module" size="small" clearable filterable placeholder="全部模块" style="width: 152px">
            <el-option v-for="name in modules" :key="name" :label="name" :value="name" />
          </el-select>
          <el-select
            v-model="filters.statuses"
            size="small"
            multiple
            collapse-tags
            clearable
            placeholder="全部发货状态"
            style="width: 152px"
          title="与表格“发货状态”列一致：台账组A日期或每日实发=已发货；计划移除=计划已移除；预计日期早于今天=已逾期；有预计发货日期且未发货=已提交待发货（计划导入自带或业务填写都算）；无预计发货日期=未提交待发货"
          >
            <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.booking_status" size="small" clearable placeholder="订舱状态" style="width: 108px">
            <el-option label="已订舱" value="已订舱" />
            <el-option label="未订舱" value="未订舱" />
          </el-select>
          <el-select v-model="filters.actual_ship_source" size="small" clearable placeholder="实际发货来源" style="width: 132px">
            <el-option label="台账" value="ledger" />
            <el-option label="系统" value="daily" />
          </el-select>
          <el-select v-model="filters.payment_ratio" size="small" clearable placeholder="回款比例" style="width: 108px">
            <el-option label="100%" value="100" />
            <el-option label="其他" value="other" />
          </el-select>
          <el-date-picker
            v-model="filters.expectedRange"
            size="small"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="预计发货起"
            end-placeholder="预计发货止"
            style="width: 212px"
          />
          <el-input v-model="filters.keyword" size="small" clearable placeholder="搜索合同号 / 梯号 / 项目" style="width: 168px" @keyup.enter="applyFilters" />
          <el-checkbox v-model="filters.include_removed" size="small" @change="applyFilters">显示已移除计划</el-checkbox>
          <el-button size="small" type="primary" @click="applyFilters">查询</el-button>
          <el-button size="small" @click="resetFilters">重置</el-button>
        </div>

        <div class="st-summary-grid">
          <div class="st-summary-card"><span>总梯号</span><strong>{{ summary.total || 0 }}</strong><small>{{ summary.units || 0 }} 台</small></div>
          <div class="st-summary-card is-green"><span>已发货</span><strong>{{ summary.shipped || 0 }}</strong><small>台账组A优先</small></div>
          <div class="st-summary-card is-blue"><span>已提交待发货</span><strong>{{ summary.committed || 0 }}</strong><small>已有预计发货日期</small></div>
          <div class="st-summary-card is-red"><span>已逾期</span><strong>{{ summary.overdue || 0 }}</strong><small>预计日期早于今天</small></div>
          <div class="st-summary-card is-gray"><span>未提交待发货</span><strong>{{ summary.pending || 0 }}</strong><small>无预计发货日期</small></div>
          <div class="st-summary-card is-cyan"><span>已订舱</span><strong>{{ summary.booked || 0 }}</strong><small>AG 列匹配</small></div>
        </div>

        <div class="st-panel">
          <div class="st-panel-head">
            <div>
              <span class="st-panel-title">发货明细</span>
              <span class="st-count">共 {{ total }} 条</span>
              <span class="st-booking-note">当前筛选：已订舱 {{ summary.booked || 0 }} / {{ summary.total || 0 }} 个梯号，报表未覆盖按「未订舱」显示</span>
              <span v-if="selectedRows.length" class="st-selected">已选 {{ selectedRows.length }} 条</span>
            </div>
            <div class="st-toolbar">
              <el-button
                v-if="(context.can_daily_edit || context.can_admin) && selectedRows.length"
                size="small"
                type="danger"
                plain
                :loading="shipmentDeleting"
                @click="handleDeleteShipments"
              >
                删除选中实发
              </el-button>
              <el-button v-if="context.can_admin && selectedRows.length" size="small" type="warning" plain @click="openUnlockDialog">
                管理员解锁选中项
              </el-button>
              <el-popover placement="bottom-end" :width="210" trigger="click">
                <template #reference>
                  <el-button size="small" plain>列设置</el-button>
                </template>
                <div class="st-column-settings">
                  <div class="st-column-title">显示更多列</div>
                  <el-checkbox-group v-model="visibleOptionalColumns" @change="saveColumnSettings">
                    <el-checkbox v-for="item in optionalColumnOptions" :key="item.key" :value="item.key">
                      {{ item.label }}
                    </el-checkbox>
                  </el-checkbox-group>
                  <el-button link type="primary" size="small" @click="resetColumnSettings">恢复默认</el-button>
                </div>
              </el-popover>
            </div>
          </div>
          <TrackingTable
            :rows="rows"
            :loading="loading"
            :selectable="context.can_admin"
            :height="tableMaxHeight"
            :optional-columns="visibleOptionalColumns"
            @selection-change="(value) => (selectedRows = value)"
            @detail="openDetail"
          />
          <el-pagination
            class="st-pager"
            layout="total, sizes, prev, pager, next"
            :total="total"
            :page-size="pageSize"
            :page-sizes="[20, 50, 100, 200]"
            :current-page="page"
            @current-change="onPageChange"
            @size-change="onPageSizeChange"
          />
        </div>
      </el-tab-pane>

      <el-tab-pane v-if="context.can_daily_edit" label="每日实发" name="daily">
        <div class="st-daily-note">
          <el-icon><InfoFilled /></el-icon>
          每日实发角色可查看全部模块。当天修正仍填写原因；填错可直接删除后重新录入，删除支持跨天且不要求填写原因。
        </div>
        <div class="st-filter-panel">
          <el-select v-model="filters.month" size="small" clearable placeholder="全部月份" style="width: 118px">
            <el-option v-for="month in months" :key="month" :label="month" :value="month" />
          </el-select>
          <el-select v-model="filters.region" size="small" clearable placeholder="全部大区" style="width: 110px">
            <el-option label="大区1" value="大区1" />
            <el-option label="大区2" value="大区2" />
          </el-select>
          <el-select v-model="filters.module" size="small" clearable filterable placeholder="全部模块" style="width: 190px">
            <el-option v-for="name in modules" :key="name" :label="name" :value="name" />
          </el-select>
          <el-input v-model="filters.keyword" size="small" clearable placeholder="搜索合同号 / 梯号 / 项目" style="width: 220px" @keyup.enter="applyFilters" />
          <el-checkbox v-model="filters.include_removed" size="small" @change="applyFilters">显示已移除计划</el-checkbox>
          <el-button size="small" type="primary" @click="applyFilters">查询</el-button>
          <el-button size="small" @click="resetFilters">重置</el-button>
        </div>
        <div class="st-daily-toolbar">
          <span class="st-toolbar-label">实发日期</span>
          <el-date-picker
            v-model="dailyDate"
            size="small"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled-date="disableFuture"
            style="width: 150px"
          />
          <el-input v-model="dailyReason" size="small" clearable placeholder="补录/修正原因（历史日期必填）" style="width: 270px" />
          <el-button type="primary" size="small" :disabled="!selectedRows.length" @click="openDailyDialog">
            录入选中梯号实发
          </el-button>
          <el-button size="small" type="danger" plain :disabled="!selectedRows.length" :loading="shipmentDeleting" @click="handleDeleteShipments">
            删除选中实发
          </el-button>
          <el-button size="small" plain @click="openExternalDialog">计划外实发</el-button>
          <span class="st-hint">已选 {{ selectedRows.length }} 条</span>
          <el-popover placement="bottom-end" :width="210" trigger="click">
            <template #reference>
              <el-button size="small" plain>列设置</el-button>
            </template>
            <div class="st-column-settings">
              <div class="st-column-title">显示更多列</div>
              <el-checkbox-group v-model="visibleOptionalColumns" @change="saveColumnSettings">
                <el-checkbox v-for="item in optionalColumnOptions" :key="item.key" :value="item.key">
                  {{ item.label }}
                </el-checkbox>
              </el-checkbox-group>
              <el-button link type="primary" size="small" @click="resetColumnSettings">恢复默认</el-button>
            </div>
          </el-popover>
        </div>
        <div class="st-panel">
          <TrackingTable
            :rows="rows"
            :loading="loading"
            :selectable="true"
            :height="tableMaxHeight"
            :optional-columns="visibleOptionalColumns"
            @selection-change="(value) => (selectedRows = value)"
            @detail="openDetail"
          />
          <el-pagination
            class="st-pager"
            layout="total, sizes, prev, pager, next"
            :total="total"
            :page-size="pageSize"
            :page-sizes="[20, 50, 100, 200]"
            :current-page="page"
            @current-change="onPageChange"
            @size-change="onPageSizeChange"
          />
        </div>
      </el-tab-pane>

      <el-tab-pane label="回款计算" name="payment">
        <div class="st-import-card st-payment-panel">
          <div class="st-payment-head">
            <div>
              <div class="st-import-title">回款比例计算</div>
              <p class="st-import-desc">
                {{ paymentStatus.data.scope_note || '只更新发货梯号明细的回款比例，不改台账、合同看板和其他模块。' }}
                台账中已满 100% 的梯号直接展示 100%；未满 100% 的梯号使用下方四类文件按梯号重新计算，结果写回「回款比例」列。
              </p>
            </div>
            <el-tag
              v-if="latestPaymentRun"
              size="small"
              :type="paymentRunStatusType(latestPaymentRun.status)"
              effect="plain"
            >
              {{ paymentRunStatusLabel(latestPaymentRun.status) }}
            </el-tag>
          </div>

          <el-alert
            v-if="paymentStatus.data.missing_labels && paymentStatus.data.missing_labels.length"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 14px"
            :title="`缺少必需文件：${paymentStatus.data.missing_labels.join('、')}，补齐后才能计算。`"
          />
          <el-alert
            v-else-if="paymentStatus.data.running"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 14px"
            title="正在计算回款比例，完成后会自动刷新主明细。"
          />
          <el-alert
            v-else-if="latestPaymentRun && latestPaymentRun.status === 'failed'"
            type="error"
            :closable="false"
            show-icon
            style="margin-bottom: 14px"
            :title="latestPaymentRun.message || '最近一次回款计算失败，请检查文件后重试。'"
          />

          <div class="st-payment-file-grid">
            <div v-for="key in paymentFileKeys" :key="key" class="st-payment-file-card">
              <div class="st-payment-file-title">
                <span>{{ paymentStatus.data.file_types?.[key]?.label || key }}</span>
                <el-tag
                  size="small"
                  :type="paymentFileTagType(paymentFile(key))"
                  effect="plain"
                >
                  {{ paymentFileTagText(paymentFile(key)) }}
                </el-tag>
              </div>
              <p class="st-payment-file-hint">{{ paymentStatus.data.file_types?.[key]?.hint || '' }}</p>
              <div v-if="paymentFile(key)" class="st-payment-file-meta">
                <span class="st-payment-filename" :title="paymentFile(key).filename">{{ paymentFile(key).filename }}</span>
                <span>{{ paymentFile(key).uploaded_at }}</span>
                <span>上传人：{{ paymentFile(key).uploaded_by_name || '—' }}</span>
              </div>
              <div v-else class="st-payment-file-meta is-empty">尚未上传</div>
              <el-upload
                :key="paymentUploadVersion[key] || 0"
                :auto-upload="false"
                :show-file-list="false"
                :accept="paymentAccept(key)"
                :on-change="(file) => handlePaymentFileChange(key, file)"
              >
                <el-button size="small" :loading="!!paymentUploading[key]">
                  {{ paymentFile(key) ? '重新上传' : '选择并上传' }}
                </el-button>
              </el-upload>
            </div>
          </div>

          <div class="st-payment-actions">
            <el-button
              size="small"
              type="primary"
              :loading="paymentCalculating"
              :disabled="!paymentStatus.data.can_calculate"
              @click="runPaymentCalc"
            >
              计算回款
            </el-button>
            <el-button size="small" :loading="paymentStatus.loading" @click="loadPaymentStatus">
              刷新状态
            </el-button>
            <el-button size="small" :disabled="!latestPaymentRun || latestPaymentRun.status === 'running'" @click="downloadPaymentAudit">
              下载审计
            </el-button>
            <span class="st-payment-note">
              台账每日上传后自动重算；点击「计算回款」可立即重算。计算期间不可重复提交。
            </span>
          </div>
        </div>

        <div v-if="latestPaymentRun" class="st-panel">
          <div class="st-panel-head">
            <span class="st-panel-title">最近计算</span>
            <div class="st-payment-run-title">
              批次 #{{ latestPaymentRun.id }} · {{ paymentTriggerLabel(latestPaymentRun.trigger_source) }} ·
              {{ latestPaymentRun.operator_name || '系统' }}
            </div>
          </div>
          <div class="st-payment-stats">
            <div><span>开始时间</span><strong>{{ latestPaymentRun.started_at || '—' }}</strong></div>
            <div><span>结束时间</span><strong>{{ latestPaymentRun.finished_at || '进行中' }}</strong></div>
            <div><span>目标梯号</span><strong>{{ latestPaymentRun.target_count ?? 0 }}</strong></div>
            <div><span>已计算</span><strong>{{ latestPaymentRun.calculated_count ?? 0 }}</strong></div>
            <div><span>更新主明细</span><strong>{{ latestPaymentRun.changed_count ?? 0 }}</strong></div>
            <div><span>保留台账比例</span><strong>{{ latestPaymentRun.kept_ledger_count ?? 0 }}</strong></div>
            <div><span>无回款记 0%</span><strong>{{ latestPaymentRun.zero_count ?? 0 }}</strong></div>
            <div><span>异常</span><strong :class="{ 'is-danger': latestPaymentRun.error_count }">{{ latestPaymentRun.error_count ?? 0 }}</strong></div>
            <div><span>数据警告</span><strong :class="{ 'is-warning': latestPaymentRun.warning_count }">{{ latestPaymentRun.warning_count ?? 0 }}</strong></div>
            <div><span>耗时</span><strong>{{ paymentDurationText(latestPaymentRun.duration_ms) }}</strong></div>
          </div>
          <el-alert
            v-if="latestPaymentRun.warning_count"
            title="计算完成，但存在需要核对的数据警告"
            :description="paymentWarningText"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
          />
          <el-alert
            v-if="latestPaymentRun.message"
            :title="latestPaymentRun.message"
            :type="latestPaymentRun.status === 'failed' ? 'error' : 'success'"
            :closable="false"
            show-icon
          />
        </div>
      </el-tab-pane>

      <el-tab-pane v-if="context.can_import" label="导入管理" name="import">
        <div class="st-import-grid">
          <div class="st-import-card">
            <div class="st-import-title">月度预计发货计划</div>
            <p class="st-import-desc">按表头名称识别列（支持新格式 A–K 与含「7日前发货」的旧格式）；自动识别重复梯号、异常日期和模块归属。重新导入会生成新版本，不删除实发与订舱事实。</p>
            <div class="st-import-form">
              <el-date-picker v-model="planMonth" size="small" type="month" value-format="YYYY-MM" placeholder="计划月份" style="width: 140px" />
              <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls" :on-change="onPlanFileChange">
                <el-button size="small">选择计划文件</el-button>
              </el-upload>
              <span class="st-file-name">{{ planFile?.name || '未选择文件' }}</span>
              <el-button size="small" type="primary" :loading="planPreviewLoading" :disabled="!planFile" @click="previewPlan">
                解析预览
              </el-button>
            </div>
            <div class="st-import-foot">
              <span>首次导入会生成版本 1；重复文件需要人工确认强制导入。</span>
              <el-button link type="primary" @click="downloadTemplate('plan')">下载模板</el-button>
            </div>
          </div>

          <div class="st-import-card">
            <div class="st-import-title">从单月填报生成计划</div>
            <p class="st-import-desc">
              取同月份各模块<strong>最新已提交版本</strong>的发货梯号，增量并入发货明细。只补缺失/已移除梯号，不改已有预计日期、实际发货、订舱和承诺；草稿不参与。
            </p>
            <div class="st-import-form">
              <el-date-picker v-model="planMonth" size="small" type="month" value-format="YYYY-MM" placeholder="计划月份" style="width: 140px" />
              <el-button size="small" type="primary" :loading="forecastPreviewLoading" @click="previewForecast">
                生成预览
              </el-button>
            </div>
            <div class="st-import-foot">
              <span>梯号必须已在台账中；未提交的模块不会包含在内。</span>
            </div>
          </div>

          <div class="st-import-card">
            <div class="st-import-title">订舱申请流程报表</div>
            <p class="st-import-desc">按 AG 列完整梯号匹配计划；主状态分为已订舱/未订舱，C 列审核状态单独展示。未出现在报表中的梯号按“未订舱”处理，导出时保留这一口径。</p>
            <div class="st-import-form">
              <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls" :on-change="onBookingFileChange">
                <el-button size="small">选择订舱文件</el-button>
              </el-upload>
              <span class="st-file-name">{{ bookingFile?.name || '未选择文件' }}</span>
              <el-button size="small" type="primary" :loading="bookingPreviewLoading" :disabled="!bookingFile" @click="previewBooking">
                解析预览
              </el-button>
            </div>
            <div class="st-import-foot">
              <span>当前报表只覆盖已导出的申请记录，不代表更早历史范围。</span>
              <el-button link type="primary" @click="downloadTemplate('booking')">下载模板</el-button>
            </div>
          </div>
        </div>

        <div class="st-import-card st-sync-card">
          <div class="st-import-title">台账字段同步</div>
          <p class="st-import-desc">
            把台账里的「排产完工日期」「整梯发货日期」「回款比例」同步到已在明细中的梯号。只更新这三个台账字段，不改模块、金额、人员、实发、订舱和承诺。
            台账日期为空会清空对应发货日期；台账里还不存在的梯号保留旧日期，但回款比例显示为空。
          </p>
          <div class="st-sync-status">
            <span>最近同步：{{ syncStatus.data.last_run_at || '尚未同步' }}</span>
            <el-tag
              v-if="syncStatus.data.status"
              size="small"
              :type="syncStatus.data.status === 'ok' ? 'success' : 'danger'"
              effect="plain"
            >
              {{ syncStatus.data.status === 'ok' ? '成功' : '失败' }}
            </el-tag>
            <span v-if="syncStatus.data.operator_name">操作人：{{ syncStatus.data.operator_name }}</span>
          </div>
          <div class="st-sync-stats">
            <span>扫描 {{ syncStatus.data.stats?.scanned ?? '—' }} 条</span>
            <span>匹配台账 {{ syncStatus.data.stats?.matched ?? '—' }} 条</span>
            <span>未匹配 {{ syncStatus.data.stats?.ledger_missing ?? '—' }} 条</span>
            <span>更新 {{ syncStatus.data.stats?.updated ?? '—' }} 条</span>
            <span>回款比例 {{ syncStatus.data.stats?.ratio_changed ?? '—' }} 条</span>
            <span>实际发货日期 {{ syncStatus.data.stats?.actual_changed ?? '—' }} 条</span>
          </div>
          <el-alert
            v-if="syncStatus.data.message"
            :title="syncStatus.data.message"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
          />
          <div class="st-import-form">
            <el-button size="small" type="primary" :loading="syncRunning" @click="runSync">立即同步</el-button>
            <el-button size="small" plain @click="loadSyncStatus">刷新状态</el-button>
          </div>
        </div>

        <div class="st-panel">
          <div class="st-panel-head">
            <span class="st-panel-title">导入批次</span>
            <div class="st-import-form">
              <el-checkbox v-model="showPreviewBatches" size="small" @change="loadImports">
                显示预览批次
              </el-checkbox>
              <el-button size="small" @click="handleCleanupPreviews">清理全部预览</el-button>
              <el-button size="small" @click="loadImports">刷新</el-button>
            </div>
          </div>
          <el-table :data="imports" size="small" border>
            <el-table-column prop="id" label="批次" width="60" />
            <el-table-column label="类型" width="80">
              <template #default="{ row }">{{ batchTypeLabel(row.data_type) }}</template>
            </el-table-column>
            <el-table-column prop="plan_month" label="月份" width="82" />
            <el-table-column prop="version" label="版本" width="60" align="center" />
            <el-table-column prop="filename" label="文件" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="batchStatusType(row.status)" effect="plain">{{ batchStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="row_count" label="行数" width="60" align="right" />
            <el-table-column prop="unique_count" label="唯一梯号" width="76" align="right" />
            <el-table-column prop="total_units" label="台数" width="58" align="right" />
            <el-table-column prop="warning_count" label="警告" width="56" align="right" />
            <el-table-column prop="error_count" label="错误" width="56" align="right" />
            <el-table-column prop="created_by_name" label="导入人" width="78" />
            <el-table-column prop="created_at" label="创建时间" width="150" />
            <el-table-column label="操作" width="110" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openIssues(row)">异常</el-button>
                <el-button
                  v-if="row.status === 'preview'"
                  link
                  type="danger"
                  size="small"
                  @click="handleDeleteBatch(row)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dailyDialog.visible" title="批量录入每日实发" width="500px">
      <el-alert type="warning" :closable="false" show-icon title="实发会立即写入全量明细。" />
      <el-form label-width="88px" class="st-dialog-form">
        <el-form-item label="实发日期">
          <el-date-picker v-model="dailyDialog.date" type="date" value-format="YYYY-MM-DD" :disabled-date="disableFuture" style="width: 100%" />
        </el-form-item>
        <el-form-item label="原因/备注">
          <el-input v-model="dailyDialog.reason" type="textarea" :rows="2" placeholder="当天正常实发可不填；历史补录必须填写" />
        </el-form-item>
      </el-form>
      <div class="st-dialog-summary">将实发 {{ selectedRows.length }} 条梯号，日期 {{ dailyDialog.date || '未选择' }}</div>
      <template #footer>
        <el-button @click="dailyDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dailySaving" @click="confirmDaily">确认实发</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="externalDialog.visible" title="计划外梯号实发" width="760px">
      <el-alert type="info" :closable="false" show-icon title="支持一次输入多个梯号，识别校验后会按每行一梯显示；/1-3# 等简写会用合同号补全前缀。" />
      <el-form label-width="88px" class="st-dialog-form">
        <el-form-item label="梯号">
          <el-input
            v-model="externalDialog.ladder_text"
            type="textarea"
            :rows="3"
            placeholder="如：DHT-261461T/1-3#、/4#、1# 3# 4#；可用换行、空格或逗号分隔"
            @input="invalidateExternalLadders"
          />
          <div class="st-dialog-summary" style="margin-top: 8px">
            <el-button size="small" :disabled="!externalDialog.ladder_text.trim()" :loading="externalParsing" @click="handleParseExternalLadders">
              识别并校验
            </el-button>
            <span class="st-hint">已识别 {{ externalDialog.ladders.length }} 台</span>
          </div>
        </el-form-item>
        <el-form-item label="合同号"><el-input v-model="externalDialog.contract_no" placeholder="简写梯号时以此作为前缀，如 261461T" @input="invalidateExternalLadders" /></el-form-item>
        <el-form-item v-if="externalDialog.parse_errors.length" label="校验">
          <el-alert type="error" :closable="false" show-icon :title="externalDialog.parse_errors.join('；')" />
        </el-form-item>
        <el-form-item v-if="externalDialog.parse_warnings.length" label="提示">
          <el-alert type="warning" :closable="false" show-icon :title="externalDialog.parse_warnings.join('；')" />
        </el-form-item>
        <el-form-item v-if="externalDialog.ladders.length" label="识别结果">
          <el-table :data="externalDialog.ladders" size="small" border max-height="220" style="width: 100%">
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="ladder_no" label="梯号" min-width="220" />
            <el-table-column label="" width="64" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" @click="removeExternalLadder($index)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
        <el-form-item label="模块">
          <el-select v-model="externalDialog.module_name" filterable style="width: 100%">
            <el-option v-for="name in modules" :key="name" :label="name" :value="name" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目名称"><el-input v-model="externalDialog.project_name" /></el-form-item>
        <el-form-item label="实发日期"><el-date-picker v-model="externalDialog.ship_date" type="date" value-format="YYYY-MM-DD" :disabled-date="disableFuture" style="width: 100%" /></el-form-item>
        <el-form-item label="原因"><el-input v-model="externalDialog.reason" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="externalDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dailySaving" :disabled="!externalDialog.ladders.length || externalDialog.parse_errors.length" @click="confirmExternal">
          确认实发
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="unlockDialog.visible" title="管理员解锁" width="520px">
      <el-form label-width="88px" class="st-dialog-form">
        <el-form-item label="解锁类型">
          <el-radio-group v-model="unlockDialog.type">
            <el-radio value="weekly">撤回周计划</el-radio>
            <el-radio value="shipment">作废实发</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="原因"><el-input v-model="unlockDialog.reason" type="textarea" :rows="3" placeholder="必填，会写入操作历史" /></el-form-item>
      </el-form>
      <div class="st-dialog-summary">将处理 {{ selectedRows.length }} 条选中梯号</div>
      <template #footer>
        <el-button @click="unlockDialog.visible = false">取消</el-button>
        <el-button type="warning" :loading="unlockSaving" @click="confirmUnlock">确认解锁</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailDrawer.visible" title="梯号详情" size="720px" class="st-detail-drawer">
      <template v-if="detailDrawer.row">
        <div class="st-detail-head">
          <div>
            <div class="st-detail-ladder">{{ detailDrawer.row.ladder_no }}</div>
            <div class="st-detail-module">{{ detailDrawer.row.module_name }}</div>
          </div>
          <el-tag :type="statusType(detailDrawer.row.status)" effect="plain">
            {{ detailDrawer.row.status_label }}
          </el-tag>
        </div>

        <el-descriptions :column="2" border size="small" label-width="92px">
          <el-descriptions-item label="合同号">{{ detailDrawer.row.contract_no || '—' }}</el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ detailDrawer.row.project_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="大区">{{ detailDrawer.row.region || '—' }}</el-descriptions-item>
          <el-descriptions-item label="模块">{{ detailDrawer.row.module_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="台数">{{ detailDrawer.row.unit_count ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="金额(万元)">{{ detailDrawer.row.amount_wan ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="排产完工日期">{{ detailDrawer.row.schedule_finish_date || '—' }}</el-descriptions-item>
          <el-descriptions-item label="整梯发货日期">{{ detailDrawer.row.whole_ship_date || '—' }}</el-descriptions-item>
          <el-descriptions-item label="预计发货">{{ detailDrawer.row.expected_ship_date || '未定' }}</el-descriptions-item>
          <el-descriptions-item label="实际发货">{{ detailDrawer.row.actual_ship_date || '未发' }}</el-descriptions-item>
          <el-descriptions-item label="实际发货来源">{{ detailDrawer.row.actual_ship_source_label || '—' }}</el-descriptions-item>
          <el-descriptions-item label="订舱状态">{{ detailDrawer.row.booking_status || '未订舱' }}</el-descriptions-item>
          <el-descriptions-item label="订舱审核">{{ detailDrawer.row.booking_audit_status || '—' }}</el-descriptions-item>
          <el-descriptions-item label="回款比例">{{ detailDrawer.row.payment_ratio_label || '—' }}</el-descriptions-item>
          <el-descriptions-item label="订舱记录">{{ detailDrawer.row.booking_record_count || 0 }} 条</el-descriptions-item>
          <el-descriptions-item label="最近申请">{{ detailDrawer.row.booking_last_date || '—' }}</el-descriptions-item>
          <el-descriptions-item label="计划变更">{{ detailDrawer.row.plan_change_count || 0 }} 次</el-descriptions-item>
          <el-descriptions-item label="数据标记">{{ detailDrawer.row.flag_labels?.length ? detailDrawer.row.flag_labels.join('；') : '—' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ sourceKindLabel(detailDrawer.row) }}</el-descriptions-item>
          <el-descriptions-item label="计划月份">{{ detailDrawer.row.plan_month || '—' }}</el-descriptions-item>
        </el-descriptions>

        <div class="st-detail-section-title">操作记录</div>
        <div class="st-detail-history" v-loading="detailDrawer.loading">
        <el-table
          v-if="detailDrawer.history.length"
          :data="detailDrawer.history"
          size="small"
          border
          max-height="360"
        >
          <el-table-column label="时间" width="132">
            <template #default="{ row }">{{ row.created_at || '—' }}</template>
          </el-table-column>
          <el-table-column label="业务类型" width="72">
            <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="84">
            <template #default="{ row }">{{ actionLabel(row.action) }}</template>
          </el-table-column>
          <el-table-column label="操作人" width="62">
            <template #default="{ row }">{{ row.operator_name || '系统' }}</template>
          </el-table-column>
          <el-table-column label="变更内容" min-width="210" show-overflow-tooltip>
            <template #default="{ row }">{{ historySummary(row) }}</template>
          </el-table-column>
          <el-table-column label="原因" min-width="90" show-overflow-tooltip>
            <template #default="{ row }">{{ row.reason || '—' }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!detailDrawer.loading" description="暂无操作记录" :image-size="56" />
        </div>
      </template>
    </el-drawer>

    <el-dialog
      v-model="planPreview.visible"
      :title="planPreview.mode === 'forecast' ? '从单月填报生成计划预览' : '月度计划导入预览'"
      width="900px"
      top="5vh"
    >
      <template v-if="planPreview.data">
        <template v-if="planPreview.mode === 'forecast'">
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item label="月份">{{ planPreview.data.plan_month }}</el-descriptions-item>
            <el-descriptions-item label="已提交模块">{{ forecastSummary.submission_module_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="填报梯号">{{ forecastSummary.selection_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="有效梯号">{{ planPreview.data.unique_count }}</el-descriptions-item>
            <el-descriptions-item label="新增">{{ forecastSummary.added_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="已存在跳过">{{ forecastSummary.existing_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="恢复已移除">{{ forecastSummary.restored_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="已实发跳过">{{ forecastSummary.skipped_shipped_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="台账未命中">{{ forecastSummary.ledger_missing_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="跨模块重复">{{ forecastSummary.duplicate_submission_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="模块不一致">{{ forecastSummary.module_mismatch_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="警告">{{ planPreview.data.warning_count }}</el-descriptions-item>
          </el-descriptions>
          <el-table :data="forecastBreakdown" size="small" border style="margin-top: 10px">
            <el-table-column prop="name" label="模块" min-width="180" />
            <el-table-column prop="version" label="提交版本" width="82" align="center" />
            <el-table-column prop="selections" label="填报梯号" width="82" align="right" />
            <el-table-column prop="added" label="新增" width="66" align="right" />
            <el-table-column prop="existing" label="已存在" width="72" align="right" />
            <el-table-column prop="restored" label="恢复" width="66" align="right" />
          </el-table>
          <el-alert
            v-if="forecastSummary.ledger_missing_count || forecastSummary.duplicate_submission_count || forecastSummary.module_mismatch_count"
            type="warning"
            :closable="false"
            show-icon
            style="margin-top: 12px"
            title="部分梯号被跳过或存在模块归属提示，请查看下方明细。"
          />
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 10px"
            title="本次只补缺失/已移除梯号，不改已有预计日期、实际发货、订舱和承诺；新增行需要业务在周填报里填写预计发货日期。"
          />
        </template>
        <template v-else>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item label="月份">{{ planPreview.data.plan_month }}</el-descriptions-item>
            <el-descriptions-item label="源数据行">{{ planPreview.data.row_count }}</el-descriptions-item>
            <el-descriptions-item label="唯一梯号">{{ planPreview.data.unique_count }}</el-descriptions-item>
            <el-descriptions-item label="有效台数">{{ planPreview.data.total_units }}</el-descriptions-item>
            <el-descriptions-item label="重复组">{{ planPreview.data.duplicate_count }}</el-descriptions-item>
            <el-descriptions-item label="新增">{{ planPreview.data.summary.added_count }}</el-descriptions-item>
            <el-descriptions-item label="将移除（纯计划行）">{{ planPreview.data.summary.removed_count }}</el-descriptions-item>
            <el-descriptions-item label="文件未含但保留">{{ planPreview.data.summary.preserved_absent_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="文件中日期与已有不同">{{ planPreview.data.summary.expected_changed_count }}</el-descriptions-item>
            <el-descriptions-item label="补空日期">{{ planPreview.data.summary.expected_filled_count ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="已提交承诺冲突（保留承诺）">{{ planPreview.data.summary.committed_conflict_count }}</el-descriptions-item>
            <el-descriptions-item label="文件未含但已实发/已订舱">{{ (planPreview.data.summary.shipped_absent_count ?? 0) + (planPreview.data.summary.booked_absent_count ?? 0) }}</el-descriptions-item>
            <el-descriptions-item label="警告">{{ planPreview.data.warning_count }}</el-descriptions-item>
            <el-descriptions-item label="错误">{{ planPreview.data.error_count }}</el-descriptions-item>
          </el-descriptions>
          <el-descriptions :column="4" border size="small" style="margin-top: 8px">
            <el-descriptions-item label="表头行">{{ planHeaderInfo.row_number || '—' }}</el-descriptions-item>
            <el-descriptions-item label="文件格式">{{ planHeaderFormatLabel }}</el-descriptions-item>
            <el-descriptions-item label="识别列数">{{ planHeaderInfo.recognized?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="数据行">{{ planPreview.data.summary.data_row_count ?? '—' }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="planHeaderInfo.recognized?.length" class="st-column-map">
            <span class="st-column-map-title">列识别</span>
            <el-tag v-for="col in planHeaderInfo.recognized" :key="col.field" size="small" effect="plain">
              {{ col.letter }}列「{{ col.header }}」→ {{ col.label }}
            </el-tag>
          </div>
          <el-alert
            v-if="ignoredColumnsText"
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 10px"
            :title="`以下列不参与计划导入：${ignoredColumnsText}`"
          />
          <el-alert
            v-if="planHeaderInfo.missing_optional?.length"
            type="warning"
            :closable="false"
            show-icon
            style="margin-top: 10px"
            :title="`未提供可选列：${planHeaderInfo.missing_optional.map((item) => item.label).join('、')}`"
          />
          <el-alert v-if="planPreview.data.summary.duplicate_import" type="warning" :closable="false" show-icon style="margin-top: 12px" title="该文件与历史已导入文件相同。如确认重新生成版本，请在下方勾选强制导入。" />
          <el-alert v-if="planPreview.data.summary.committed_conflict_count" type="error" :closable="false" show-icon style="margin-top: 12px" title="文件中的日期与已提交承诺不一致。系统保留原承诺并标记冲突，不会静默覆盖。" />
          <el-alert type="info" :closable="false" show-icon style="margin-top: 10px" title="默认保留已有预计/实际/订舱/承诺，只有空值才会被文件补上。勾选下方选项后，已有预计日期才会按文件更新，实际发货/订舱/承诺仍不变。" />
        </template>
        <el-table :data="planPreview.data.issues.slice(0, 200)" size="small" border max-height="300" style="margin-top: 12px">
          <el-table-column prop="row_number" label="行号" width="65" align="center" />
          <el-table-column prop="severity" label="级别" width="75" />
          <el-table-column prop="message" label="提示" min-width="480" />
        </el-table>
        <div class="st-preview-foot">
          <template v-if="planPreview.mode !== 'forecast'">
            <el-checkbox v-model="planPreview.force">强制重新导入相同文件</el-checkbox>
            <el-checkbox v-model="planPreview.overwriteExpected">用文件中的预计日期覆盖已有预计日期</el-checkbox>
          </template>
          <span>预览共 {{ planPreview.data.issue_total || 0 }} 条提示</span>
        </div>
      </template>
      <template #footer>
        <el-button @click="planPreview.visible = false">取消</el-button>
        <el-button type="primary" :loading="planCommitLoading" @click="commitPlan">
          {{ planPreview.mode === 'forecast' ? '确认并入明细' : '确认生成版本' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bookingPreview.visible" title="订舱报表导入预览" width="860px">
      <template v-if="bookingPreview.data">
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="有效行">{{ bookingPreview.data.row_count }}</el-descriptions-item>
          <el-descriptions-item label="唯一梯号">{{ bookingPreview.data.unique_count }}</el-descriptions-item>
          <el-descriptions-item label="匹配当前计划">{{ bookingPreview.data.summary.matched_plan_count }}</el-descriptions-item>
          <el-descriptions-item label="未匹配计划">{{ bookingPreview.data.summary.unmatched_plan_count }}</el-descriptions-item>
          <el-descriptions-item label="预览已订舱">{{ bookingPreview.data.summary.preview_booked_count }}</el-descriptions-item>
          <el-descriptions-item label="空白 AG 行">{{ bookingPreview.data.summary.blank_ladder_count }}</el-descriptions-item>
          <el-descriptions-item label="多状态梯号">{{ bookingPreview.data.summary.multiple_ladder_count }}</el-descriptions-item>
          <el-descriptions-item label="将重置为未订舱">{{ bookingPreview.data.summary.reset_count }}</el-descriptions-item>
          <el-descriptions-item label="警告">{{ bookingPreview.data.warning_count }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="bookingPreview.data.summary.reset_count"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 10px"
          :title="`提交后，未出现在本报表中的 ${bookingPreview.data.summary.reset_count} 条追踪行会被重置为「未订舱」；AG 列为空的行不参与匹配。`"
        />
        <div v-if="bookingPreview.data.summary.reset_sample?.length" class="st-status-line">
          <span class="st-hint">将被重置的梯号示例（前 20 条）：</span>
          <span v-for="key in bookingPreview.data.summary.reset_sample.slice(0, 20)" :key="key" class="st-status-chip">{{ key }}</span>
        </div>
        <div class="st-status-line">
          <span v-for="(count, status) in bookingPreview.data.summary.status_counts" :key="status" class="st-status-chip">
            {{ status }}：{{ count }}
          </span>
        </div>
        <el-table :data="bookingPreview.data.issues.slice(0, 200)" size="small" border max-height="300" style="margin-top: 12px">
          <el-table-column prop="row_number" label="行号" width="65" align="center" />
          <el-table-column prop="severity" label="级别" width="75" />
          <el-table-column prop="message" label="提示" min-width="480" />
        </el-table>
        <div class="st-preview-foot">
          <el-checkbox v-model="bookingPreview.force">强制重新导入相同文件</el-checkbox>
          <span>预览共 {{ bookingPreview.data.issue_total || 0 }} 条提示</span>
        </div>
      </template>
      <template #footer>
        <el-button @click="bookingPreview.visible = false">取消</el-button>
        <el-button type="primary" :loading="bookingCommitLoading" @click="commitBooking">确认更新订舱状态</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="issuesDialog.visible" title="导入异常与警告" width="800px">
      <div class="st-history-head">{{ issuesDialog.batch?.filename }}</div>
      <el-table :data="issuesDialog.rows" size="small" border max-height="500">
        <el-table-column prop="row_number" label="行号" width="65" align="center" />
        <el-table-column prop="severity" label="级别" width="80" />
        <el-table-column prop="code" label="代码" width="160" />
        <el-table-column prop="message" label="提示" min-width="430" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calculatePayment,
  cleanupPreviewBatches,
  commitBookingImport,
  commitForecastImport,
  commitPlanImport,
  deleteDailyShipments,
  deleteImportBatch,
  downloadImportTemplate,
  downloadPaymentReport,
  downloadTrackingExport,
  getImportBatches,
  getImportIssues,
  getPaymentStatus,
  getSyncStatus,
  getTrackingHistory,
  getTrackingItems,
  previewBookingImport,
  previewExternalLadders,
  previewPlanFromForecast,
  previewPlanImport,
  recordDailyShipments,
  syncTrackingDates,
  unlockShipTracking,
  uploadPaymentFile,
} from '../../api/shipTracking'
import TrackingTable from './TrackingTable.vue'

const props = defineProps({
  context: { type: Object, required: true },
})
const emit = defineEmits(['refresh-context'])

const activeTab = ref('tracking')
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const modules = ref([])
const months = ref([])
const summary = ref({})
const selectedRows = ref([])
const statusOptions = [
  { value: 'shipped', label: '已发货' },
  { value: 'overdue', label: '已逾期' },
  { value: 'committed', label: '已提交待发货' },
  { value: 'pending', label: '未提交待发货' },
  { value: 'removed', label: '计划已移除' },
]
const filters = reactive({
  month: props.context.default_month || '',
  module: '',
  region: '',
  statuses: [],
  booking_status: '',
  actual_ship_source: '',
  payment_ratio: '',
  keyword: '',
  expectedRange: [],
  include_removed: false,
})
const dailyDate = ref(props.context.today)
const dailyReason = ref('')
const dailySaving = ref(false)
const shipmentDeleting = ref(false)
const externalParsing = ref(false)
const dailyDialog = reactive({ visible: false, date: props.context.today, reason: '' })
const externalDialog = reactive({
  visible: false, ladder_text: '', contract_no: '', module_name: '', project_name: '',
  ship_date: props.context.today, reason: '', ladders: [], parse_errors: [], parse_warnings: [],
})
const unlockDialog = reactive({ visible: false, type: 'weekly', reason: '' })
const unlockSaving = ref(false)
const detailDrawer = reactive({ visible: false, loading: false, row: null, history: [] })

const COLUMN_SETTINGS_KEY = 'ship-tracking-optional-columns'
const optionalColumnOptions = [
  { key: 'amount', label: '金额(万元)' },
  { key: 'schedule', label: '排产完工日期' },
  { key: 'whole', label: '整梯发货日期' },
  { key: 'flags', label: '计划变更 / 异常' },
]
const optionalColumnKeys = optionalColumnOptions.map((item) => item.key)
const visibleOptionalColumns = ref(loadColumnSettings() || [])

function loadColumnSettings() {
  try {
    const stored = JSON.parse(localStorage.getItem(COLUMN_SETTINGS_KEY) || '[]')
    return Array.isArray(stored) ? stored.filter((key) => optionalColumnKeys.includes(key)) : []
  } catch (error) {
    return []
  }
}

function saveColumnSettings() {
  try {
    localStorage.setItem(COLUMN_SETTINGS_KEY, JSON.stringify(visibleOptionalColumns.value))
  } catch (error) {
    // 浏览器禁用本地存储时忽略
  }
  nextTick(updateTableMaxHeight)
}

function resetColumnSettings() {
  visibleOptionalColumns.value = []
  saveColumnSettings()
}

const planMonth = ref(props.context.default_month)
const planFile = ref(null)
const planPreview = reactive({
  visible: false,
  data: null,
  force: false,
  overwriteExpected: false,
  mode: 'excel',
})
const planPreviewLoading = ref(false)
const planCommitLoading = ref(false)
const forecastPreviewLoading = ref(false)
const forecastSummary = computed(() => planPreview.data?.summary || {})
const forecastBreakdown = computed(() => {
  const entries = forecastSummary.value.module_breakdown || {}
  return Object.keys(entries).sort().map((name) => ({ name, ...entries[name] }))
})
const planHeaderInfo = computed(() => planPreview.data?.summary?.header || {})
const planHeaderFormatLabel = computed(() => ({
  new: '新格式（业务预计发货时间）',
  legacy: '旧格式（7日前发货）',
  hybrid: '兼容格式（业务预计 + 7日前发货）',
}[planHeaderInfo.value.format] || '未识别'))
const ignoredColumnsText = computed(() => {
  const list = [...(planHeaderInfo.value.ignored || []), ...(planHeaderInfo.value.unknown || [])]
  return list.map((col) => `${col.letter}列「${col.header}」`).join('、')
})
const bookingFile = ref(null)
const bookingPreview = reactive({ visible: false, data: null, force: false })
const bookingPreviewLoading = ref(false)
const bookingCommitLoading = ref(false)
const imports = ref([])
const showPreviewBatches = ref(false)
const issuesDialog = reactive({ visible: false, batch: null, rows: [] })

const exportFilename = computed(() => `${filters.month || '全部'}_发货梯号明细.xlsx`)

const tableMaxHeight = ref(560)

function updateTableMaxHeight() {
  const panels = Array.from(document.querySelectorAll('.st-panel'))
  const panel = panels.find((el) => el.offsetParent !== null && el.querySelector('.st-table'))
  if (!panel) {
    tableMaxHeight.value = Math.max(240, Math.min(760, window.innerHeight - 380))
    return
  }
  const table = panel.querySelector('.st-table')
  const pager = panel.querySelector('.st-pager')
  const top = panel.getBoundingClientRect().top
  const tableTop = table.getBoundingClientRect().top
  if (!panel.offsetHeight || tableTop <= top) {
    tableMaxHeight.value = Math.max(200, Math.min(760, window.innerHeight - top - 164))
    return
  }
  const page = document.querySelector('.st-page')
  const main = document.querySelector('.el-main.user-main')
  const px = (value) => parseFloat(value) || 0
  // 表头/面板上内边距 + 分页 + 面板下内边距 + 页面和主区域的下留白。
  // 把这些都算进去，内容正好落在可视区，主区域不会因为底部空白出现多余滚动条。
  const chrome = (tableTop - top) + (pager ? pager.offsetHeight + 8 : 50) + 12
  const bottomSpace = (page ? px(getComputedStyle(page).paddingBottom) : 0)
    + (main ? px(getComputedStyle(main).paddingBottom) : 0)
  const available = window.innerHeight - top - chrome - bottomSpace - 2
  tableMaxHeight.value = Math.max(200, Math.min(760, available))
}

function buildParams(extra = {}) {
  const params = {
    month: filters.month,
    module: filters.module,
    region: filters.region,
    booking_status: filters.booking_status,
    actual_ship_source: filters.actual_ship_source,
    payment_ratio: filters.payment_ratio,
    keyword: filters.keyword,
    include_removed: filters.include_removed ? 1 : '',
    page: page.value,
    page_size: pageSize.value,
    ...extra,
  }
  if (filters.statuses.length) params.status = filters.statuses.join(',')
  if (filters.expectedRange?.length === 2) {
    params.expected_start = filters.expectedRange[0]
    params.expected_end = filters.expectedRange[1]
  }
  return params
}

async function loadData() {
  loading.value = true
  try {
    const res = await getTrackingItems(buildParams())
    rows.value = res.data.items || []
    total.value = res.data.total || 0
    summary.value = res.data.summary || {}
    modules.value = res.data.modules || []
    months.value = res.data.months || []
    selectedRows.value = []
  } catch (error) {
    // 拦截器已提示
  } finally {
    loading.value = false
    await nextTick()
    updateTableMaxHeight()
  }
}

function applyFilters() {
  page.value = 1
  loadData()
}

function resetFilters() {
  filters.month = props.context.default_month || ''
  filters.module = ''
  filters.region = ''
  filters.statuses = []
  filters.booking_status = ''
  filters.actual_ship_source = ''
  filters.payment_ratio = ''
  filters.keyword = ''
  filters.expectedRange = []
  filters.include_removed = false
  page.value = 1
  loadData()
}

function onPageChange(value) {
  page.value = value
  loadData()
}

function onPageSizeChange(value) {
  pageSize.value = value
  page.value = 1
  loadData()
}

async function handleTabChange(name) {
  selectedRows.value = []
  if (name === 'daily') {
    // 每日实发页没有状态/订舱/预计日期筛选，切过去时清掉全量页遗留的隐藏筛选，
    // 否则列表和导出会被看不见的条件限制。
    filters.statuses = []
    filters.booking_status = ''
    filters.actual_ship_source = ''
    filters.payment_ratio = ''
    filters.expectedRange = []
    page.value = 1
    loadData()
  }
  if (name === 'import') {
    loadImports()
    loadSyncStatus()
  }
  if (name === 'payment') {
    await loadPaymentStatus()
    if (paymentStatus.data.running) startPaymentPolling()
  }
  nextTick(updateTableMaxHeight)
}

const syncStatus = reactive({ loading: false, data: {} })
const syncRunning = ref(false)

const paymentFileKeys = ['table_b', 'table_e', 'table_r', 'exchange_rate']
const paymentStatus = reactive({ loading: false, data: {} })
const paymentUploading = reactive({})
const paymentUploadVersion = reactive({})
const paymentCalculating = ref(false)
let paymentPollTimer = null
const latestPaymentRun = computed(
  () => paymentStatus.data.running || paymentStatus.data.last_run || null,
)
const paymentWarningText = computed(() => {
  const warnings = latestPaymentRun.value?.stats?.warnings || []
  if (!warnings.length) return '详见下载审计的「异常清单」。'
  const shown = warnings.slice(0, 5).join('；')
  return warnings.length > 5 ? `${shown}；另有 ${warnings.length - 5} 条，详见审计文件。` : shown
})

function paymentFile(key) {
  return paymentStatus.data.files?.[key] || null
}

function paymentAccept(key) {
  const extensions = paymentStatus.data.file_types?.[key]?.extensions
  const fallback = key === 'exchange_rate' ? ['.txt'] : ['.xlsx', '.xls']
  return (extensions && extensions.length ? extensions : fallback).join(',')
}

function paymentFileTagText(file) {
  if (!file) return '未上传'
  if (file.status === 'validated') return '已校验'
  if (file.status === 'stored') return '已上传'
  return '异常'
}

function paymentFileTagType(file) {
  if (!file) return 'info'
  if (file.status === 'validated' || file.status === 'stored') return 'success'
  return 'danger'
}

function paymentRunStatusLabel(status) {
  return {
    running: '计算中',
    success: '计算成功',
    failed: '计算失败',
    skipped: '已跳过',
  }[status] || status || '—'
}

function paymentRunStatusType(status) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

function paymentTriggerLabel(trigger) {
  if (trigger === 'manual') return '手动计算'
  if (trigger === 'auto:ledger_sync') return '台账更新自动重算'
  return trigger || '系统'
}

function paymentDurationText(durationMs) {
  const value = Number(durationMs) || 0
  if (!value) return '—'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} 秒`
}

async function loadPaymentStatus(silent = false) {
  if (!silent) paymentStatus.loading = true
  try {
    const res = await getPaymentStatus()
    paymentStatus.data = res.data || {}
  } catch (error) {
    // 拦截器已提示
  } finally {
    if (!silent) paymentStatus.loading = false
  }
}

async function handlePaymentFileChange(fileType, uploadFile) {
  const raw = uploadFile?.raw
  if (!raw) return
  paymentUploading[fileType] = true
  try {
    await uploadPaymentFile(fileType, raw)
    const label = paymentStatus.data.file_types?.[fileType]?.label || fileType
    ElMessage.success(`${label}上传成功，文件校验通过`)
    await loadPaymentStatus(true)
  } catch (error) {
    // 拦截器已提示
  } finally {
    paymentUploading[fileType] = false
    // 允许同名文件再次选择：重挂上传组件，清掉内部已选文件，否则浏览器可能不触发 change。
    paymentUploadVersion[fileType] = (paymentUploadVersion[fileType] || 0) + 1
  }
}

function stopPaymentPolling() {
  if (paymentPollTimer) {
    clearInterval(paymentPollTimer)
    paymentPollTimer = null
  }
}

function startPaymentPolling() {
  stopPaymentPolling()
  paymentCalculating.value = true
  paymentPollTimer = setInterval(async () => {
    await loadPaymentStatus(true)
    if (paymentStatus.data.running) return
    stopPaymentPolling()
    paymentCalculating.value = false
    await loadData()
    const run = paymentStatus.data.last_run
    if (run?.status === 'success') {
      ElMessage.success(`回款计算完成：更新 ${run.changed_count || 0} 条，异常 ${run.error_count || 0} 条`)
    } else if (run?.status === 'failed') {
      ElMessage.error(run.message || '回款计算失败，请检查文件')
    }
  }, 3000)
}

async function runPaymentCalc() {
  try {
    await ElMessageBox.confirm(
      '将使用当前四类文件重新计算所有未满 100% 的梯号，并把结果写回发货梯号明细的「回款比例」列。只影响本模块，不修改台账和其他看板。是否开始？',
      '计算回款比例',
      { type: 'warning', confirmButtonText: '开始计算', cancelButtonText: '取消' },
    )
  } catch (error) {
    return
  }
  paymentCalculating.value = true
  try {
    const res = await calculatePayment(true)
    const data = res.data || {}
    if (data.started) {
      ElMessage.success('回款计算已开始，完成后会自动刷新主明细')
      await loadPaymentStatus(true)
      startPaymentPolling()
    } else if (data.finished) {
      ElMessage.success(data.message || '回款计算完成')
      await loadPaymentStatus()
      await loadData()
      paymentCalculating.value = false
    } else {
      ElMessage.warning(data.message || '计算未启动')
      await loadPaymentStatus()
      paymentCalculating.value = false
    }
  } catch (error) {
    paymentCalculating.value = false
  }
}

async function downloadPaymentAudit() {
  const run = latestPaymentRun.value
  if (!run || run.status === 'running') return
  try {
    const blob = await downloadPaymentReport(run.id)
    saveBlob(blob, `回款计算审计_${run.id}.xlsx`)
    ElMessage.success('审计文件已开始下载')
  } catch (error) {
    // 拦截器已提示
  }
}

async function loadSyncStatus() {
  if (!props.context.can_admin) return
  syncStatus.loading = true
  try {
    const res = await getSyncStatus()
    syncStatus.data = res.data || {}
  } catch (error) {
    // 拦截器已提示
  } finally {
    syncStatus.loading = false
  }
}

async function runSync() {
  try {
    await ElMessageBox.confirm(
      '同步只更新「排产完工日期」「整梯发货日期」「回款比例」；台账日期为空会清空对应发货日期，台账无此梯号时回款比例会清空，不会修改实发、订舱、承诺、模块和人员。是否继续？',
      '台账字段同步',
      { type: 'warning', confirmButtonText: '开始同步', cancelButtonText: '取消' },
    )
  } catch (error) {
    return
  }
  syncRunning.value = true
  try {
    const res = await syncTrackingDates()
    const data = res.data || {}
    if (data.skipped) {
      ElMessage.warning(data.message || '已有同步任务在运行')
    } else if (data.ok) {
      ElMessage.success(
        `同步完成：更新 ${data.updated || 0} 条（其中回款比例 ${data.ratio_changed || 0} 条，实际发货日期 ${data.actual_changed || 0} 条），未匹配台账 ${data.ledger_missing || 0} 条`
      )
    } else {
      ElMessage.error(data.message || '同步失败')
    }
    await loadSyncStatus()
    await loadData()
  } catch (error) {
    // 拦截器已提示
  } finally {
    syncRunning.value = false
  }
}

async function handleExport() {
  try {
    const params = buildParams({ page: 1, page_size: 'all' })
    delete params.page
    delete params.page_size
    const blob = await downloadTrackingExport({ ...params, page_size: 'all' })
    saveBlob(blob, exportFilename.value)
    ElMessage.success('导出已开始下载')
  } catch (error) {
    // 拦截器已提示
  }
}

async function downloadTemplate(type) {
  try {
    const blob = await downloadImportTemplate(type)
    saveBlob(blob, type === 'booking' ? '订舱申请流程报表_导入模板.xlsx' : '预计发货合同梯号明细_导入模板.xlsx')
  } catch (error) {
    // 拦截器已提示
  }
}

function saveBlob(blob, filename) {
  const data = blob instanceof Blob ? blob : new Blob([blob])
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function disableFuture(date) {
  const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  return value > props.context.today
}

function openDailyDialog() {
  if (!selectedRows.value.length) return ElMessage.warning('请选择要实发的梯号')
  if (!dailyDate.value) return ElMessage.warning('请选择实发日期')
  dailyDialog.visible = true
  dailyDialog.date = dailyDate.value
  dailyDialog.reason = dailyReason.value
}

async function confirmDaily() {
  dailySaving.value = true
  try {
    const res = await recordDailyShipments({
      reason: dailyDialog.reason,
      items: selectedRows.value.map((row) => ({
        ladder_key: row.ladder_key,
        ship_date: dailyDialog.date,
        unit_count: row.unit_count,
      })),
    })
    ElMessage.success(`已录入 ${res.data.shipped} 条实发`)
    dailyDialog.visible = false
    dailyReason.value = ''
    await loadData()
    emit('refresh-context')
  } catch (error) {
    // 拦截器已提示
  } finally {
    dailySaving.value = false
  }
}

async function handleDeleteShipments() {
  const selected = selectedRows.value
  if (!selected.length) return ElMessage.warning('请选择要删除的实发梯号')
  const eligible = selected.filter((row) => row.actual_ship_source === 'daily')
  if (!eligible.length) return ElMessage.warning('选中梯号没有可删除的系统实发记录')
  const skipped = selected.length - eligible.length
  try {
    await ElMessageBox.confirm(
      `将删除 ${eligible.length} 条系统实发记录` +
        (skipped ? `，跳过 ${skipped} 条非系统实发或未实发记录` : '') +
        '。删除后梯号会回到未实发状态；如台账仍有发货日期，继续以台账为准。是否继续？',
      '删除实发',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  shipmentDeleting.value = true
  try {
    const res = await deleteDailyShipments({
      ladder_keys: eligible.map((row) => row.ladder_key),
    })
    const data = res.data || {}
    ElMessage.success(
      `已删除 ${data.deleted || 0} 条实发` +
        (data.skipped ? `，跳过 ${data.skipped} 条` : '')
    )
    await loadData()
    emit('refresh-context')
  } catch (error) {
    // 拦截器已提示
  } finally {
    shipmentDeleting.value = false
  }
}

function invalidateExternalLadders() {
  externalDialog.ladders = []
  externalDialog.parse_errors = []
  externalDialog.parse_warnings = []
}

function removeExternalLadder(index) {
  externalDialog.ladders.splice(index, 1)
}

async function handleParseExternalLadders() {
  if (!externalDialog.ladder_text.trim()) return ElMessage.warning('请输入梯号')
  externalParsing.value = true
  try {
    const res = await previewExternalLadders({
      ladder_no: externalDialog.ladder_text,
      contract_no: externalDialog.contract_no,
    })
    const data = res.data || {}
    externalDialog.ladders = (data.ladders || []).map((ladder) => ({ ladder_no: ladder }))
    externalDialog.parse_errors = data.errors || []
    externalDialog.parse_warnings = data.warnings || []
    if (externalDialog.ladders.length) {
      ElMessage.success(`已识别 ${externalDialog.ladders.length} 台梯号`)
    } else {
      ElMessage.warning(externalDialog.parse_errors[0] || '未识别到有效梯号')
    }
  } catch (error) {
    // 拦截器已提示
  } finally {
    externalParsing.value = false
  }
}

function openExternalDialog() {
  Object.assign(externalDialog, {
    visible: true,
    ladder_text: '',
    contract_no: '',
    module_name: filters.module || '',
    project_name: '',
    ship_date: props.context.today,
    reason: '',
    ladders: [],
    parse_errors: [],
    parse_warnings: [],
  })
}

async function confirmExternal() {
  if (!externalDialog.module_name) return ElMessage.warning('模块必填')
  if (!externalDialog.ladders.length) return ElMessage.warning('请先识别梯号')
  if (externalDialog.parse_errors.length) return ElMessage.warning('请先处理梯号校验错误')
  const ladders = externalDialog.ladders.map((row) => (row.ladder_no || '').trim()).filter(Boolean)
  if (!ladders.length) return ElMessage.warning('请至少保留一个梯号')
  if (new Set(ladders).size !== ladders.length) return ElMessage.warning('识别结果中存在重复梯号，请重新识别')
  dailySaving.value = true
  try {
    const res = await recordDailyShipments({
      reason: externalDialog.reason,
      items: ladders.map((ladder) => ({
        ladder_key: ladder,
        ladder_no: ladder,
        contract_no: externalDialog.contract_no,
        module_name: externalDialog.module_name,
        project_name: externalDialog.project_name,
        ship_date: externalDialog.ship_date,
      })),
    })
    ElMessage.success(`已录入 ${res.data.shipped} 条计划外实发`)
    externalDialog.visible = false
    await loadData()
    emit('refresh-context')
  } catch (error) {
    // 拦截器已提示
  } finally {
    dailySaving.value = false
  }
}

function openUnlockDialog() {
  if (!selectedRows.value.length) return ElMessage.warning('请选择梯号')
  unlockDialog.visible = true
  unlockDialog.type = 'weekly'
  unlockDialog.reason = ''
}

async function confirmUnlock() {
  if (!unlockDialog.reason.trim()) return ElMessage.warning('请填写解锁原因')
  unlockSaving.value = true
  try {
    const res = await unlockShipTracking({
      type: unlockDialog.type,
      reason: unlockDialog.reason,
      ladder_keys: selectedRows.value.map((row) => row.ladder_key),
    })
    const skippedHint = unlockDialog.type === 'shipment'
      ? '无有效实发记录，未改动'
      : '非已提交状态，未改动'
    ElMessage.success(
      `已处理 ${res.data.unlocked || 0} 条` +
        (res.data.skipped ? `，跳过 ${res.data.skipped} 条（${skippedHint}）` : '')
    )
    unlockDialog.visible = false
    await loadData()
  } catch (error) {
    // 拦截器已提示
  } finally {
    unlockSaving.value = false
  }
}

async function openDetail(row) {
  detailDrawer.row = row
  detailDrawer.history = []
  detailDrawer.visible = true
  detailDrawer.loading = true
  try {
    const res = await getTrackingHistory(row.ladder_key)
    detailDrawer.history = res.data || []
  } catch (error) {
    // 拦截器已提示
  } finally {
    detailDrawer.loading = false
  }
}

const CATEGORY_LABELS = {
  plan: '计划导入',
  forecast: '单月填报',
  weekly: '周填报',
  daily: '每日实发',
  import: '导入批次',
  sync: '台账同步',
}
const ACTION_LABELS = {
  add: '新增计划',
  update: '计划变更',
  remove: '计划移除',
  submit: '提交周计划',
  withdraw: '撤回周计划',
  adjust: '同周改期',
  draft_save: '保存草稿',
  create_shipment: '录入实发',
  update_shipment: '修正实发',
  delete_shipment: '删除实发',
  admin_void_shipment: '作废实发',
  admin_unlock: '管理员解锁',
  commit_plan: '生效计划版本',
  commit_booking: '更新订舱状态',
  commit_forecast: '并入单月填报',
  delete_preview_batch: '删除预览批次',
  cleanup_preview_batches: '清理预览批次',
  restore: '恢复计划',
  manual_add: '手工新增梯号',
  sync_run: '执行同步',
  sync_update: '同步台账字段',
}
const FIELD_LABELS = {
  expected_ship_date: '预计发货',
  draft_expected_ship_date: '草稿预计发货',
  draft_week_start: '草稿周',
  committed_week_start: '承诺周',
  module_name: '模块',
  schedule_finish_date: '排产完工日期',
  whole_ship_date: '整梯发货日期',
  payment_ratio: '回款比例',
  unit_count: '台数',
  amount_rmb: '金额(元)',
  plan_status: '计划状态',
  ship_date: '实发日期',
  plan_month: '计划月份',
  version: '版本',
  unique_count: '唯一梯号',
  changed_count: '变更条数',
}
const VALUE_LABELS = {
  removed: '已移除',
  active: '有效',
  committed: '已提交',
}

function categoryLabel(value) {
  return CATEGORY_LABELS[value] || value || '—'
}
function actionLabel(value) {
  return ACTION_LABELS[value] || value || '—'
}
function formatFieldValue(key, value) {
  if (value === null || value === undefined || value === '') return '空'
  if (VALUE_LABELS[value]) return VALUE_LABELS[value]
  if (key === 'amount_rmb' && Number.isFinite(Number(value))) {
    return `${(Number(value) / 10000).toFixed(2)} 万元`
  }
  if (key === 'payment_ratio' && Number.isFinite(Number(value))) {
    return `${(Math.min(1, Math.max(0, Number(value))) * 100).toFixed(2)}%`
  }
  return String(value)
}
function historySummary(row) {
  const oldValues = row.old_values || {}
  const newValues = row.new_values || {}
  const keys = Object.keys(newValues)
  if (!keys.length) return '—'
  const parts = []
  for (const key of keys) {
    const label = FIELD_LABELS[key] || key
    const before = formatFieldValue(key, oldValues[key])
    const after = formatFieldValue(key, newValues[key])
    if (before === after) continue
    parts.push(`${label}：${before} → ${after}`)
  }
  return parts.length ? parts.join('；') : '无字段变化'
}

function statusType(status) {
  if (status === 'shipped') return 'success'
  if (status === 'overdue') return 'danger'
  if (status === 'committed') return 'primary'
  if (status === 'removed') return 'info'
  return 'warning'
}

function onPlanFileChange(file) {
  planFile.value = file.raw || file
}
function onBookingFileChange(file) {
  bookingFile.value = file.raw || file
}

async function previewPlan() {
  if (!planFile.value) return
  planPreviewLoading.value = true
  try {
    const res = await previewPlanImport(planFile.value, planMonth.value)
    planPreview.data = res.data
    planPreview.force = false
    planPreview.overwriteExpected = false
    planPreview.mode = 'excel'
    planPreview.visible = true
  } catch (error) {
    // 拦截器已提示
  } finally {
    planPreviewLoading.value = false
  }
}

async function previewForecast() {
  if (!planMonth.value) {
    ElMessage.warning('请先选择计划月份')
    return
  }
  forecastPreviewLoading.value = true
  try {
    const res = await previewPlanFromForecast(planMonth.value)
    planPreview.data = res.data
    planPreview.force = false
    planPreview.overwriteExpected = false
    planPreview.mode = 'forecast'
    planPreview.visible = true
  } catch (error) {
    // 拦截器已提示
  } finally {
    forecastPreviewLoading.value = false
  }
}

async function commitPlan() {
  planCommitLoading.value = true
  try {
    if (planPreview.mode === 'forecast') {
      const res = await commitForecastImport(planPreview.data.id)
      const data = res.data || {}
      ElMessage.success(
        `已并入 ${data.added_count || 0} 条，恢复 ${data.restored_count || 0} 条，已存在跳过 ${data.skipped_existing || 0} 条`
      )
    } else {
      const res = await commitPlanImport(
        planPreview.data.id,
        planPreview.force,
        planPreview.overwriteExpected
      )
      const preserved = res.data.preserved_absent_count || 0
      ElMessage.success(
        `计划版本 ${res.data.version} 已生效，变更 ${res.data.changed_count} 条` +
          (preserved ? `，文件未含但保留 ${preserved} 条` : '')
      )
      planFile.value = null
    }
    planPreview.visible = false
    await loadData()
    await loadImports()
  } catch (error) {
    // 拦截器已提示
  } finally {
    planCommitLoading.value = false
  }
}

async function previewBooking() {
  if (!bookingFile.value) return
  bookingPreviewLoading.value = true
  try {
    const res = await previewBookingImport(bookingFile.value)
    bookingPreview.data = res.data
    bookingPreview.force = false
    bookingPreview.visible = true
  } catch (error) {
    // 拦截器已提示
  } finally {
    bookingPreviewLoading.value = false
  }
}

async function commitBooking() {
  bookingCommitLoading.value = true
  try {
    const res = await commitBookingImport(bookingPreview.data.id, bookingPreview.force)
    ElMessage.success(
      `订舱状态已更新，匹配 ${res.data.matched_plan_count} 条计划梯号` +
        (res.data.reset_count ? `，另有 ${res.data.reset_count} 条重置为未订舱` : '')
    )
    bookingPreview.visible = false
    bookingFile.value = null
    await loadData()
    await loadImports()
  } catch (error) {
    // 拦截器已提示
  } finally {
    bookingCommitLoading.value = false
  }
}

async function loadImports() {
  try {
    const res = await getImportBatches('', showPreviewBatches.value)
    imports.value = res.data || []
  } catch (error) {
    // 拦截器已提示
  }
}

async function handleDeleteBatch(batch) {
  try {
    await ElMessageBox.confirm(
      `删除预览批次 #${batch.id}（${batch.filename || '未命名文件'}）？只清理未提交的预览，不影响已生效数据。`,
      '删除预览批次',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await deleteImportBatch(batch.id)
    ElMessage.success('预览批次已删除')
    await loadImports()
  } catch (error) {
    // 拦截器已提示
  }
}

async function handleCleanupPreviews() {
  try {
    await ElMessageBox.confirm(
      '清理所有未提交的预览批次？已生效、已替代的批次不受影响。',
      '清理全部预览',
      { type: 'warning', confirmButtonText: '清理', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    const res = await cleanupPreviewBatches()
    ElMessage.success(`已清理 ${res.data?.deleted || 0} 个预览批次`)
    await loadImports()
  } catch (error) {
    // 拦截器已提示
  }
}

async function openIssues(batch) {
  try {
    const res = await getImportIssues(batch.id)
    issuesDialog.batch = res.data.batch
    issuesDialog.rows = res.data.issues || []
    issuesDialog.visible = true
  } catch (error) {
    // 拦截器已提示
  }
}

function sourceKindLabel(row) {
  if (!row) return '—'
  if (row.source_kind === 'actual_only') return '计划外实发'
  if (row.source_kind === 'manual') return '业务手工新增'
  if ((row.data_flags || []).includes('from_monthly_forecast')) return '单月填报生成'
  return row.source || '月度计划'
}

function batchTypeLabel(dataType) {
  if (dataType === 'plan') return '月度计划'
  if (dataType === 'plan_forecast') return '单月填报'
  if (dataType === 'booking') return '订舱报表'
  return dataType || '—'
}

function batchStatusLabel(status) {
  if (status === 'committed') return '已生效'
  if (status === 'preview') return '预览'
  if (status === 'superseded') return '历史版本'
  return '失败'
}
function batchStatusType(status) {
  if (status === 'committed') return 'success'
  if (status === 'preview') return 'warning'
  return 'info'
}

onMounted(async () => {
  months.value = props.context.months || []
  updateTableMaxHeight()
  window.addEventListener('resize', updateTableMaxHeight)
  await loadData()
  if (props.context.can_admin) {
    await loadImports()
    await loadSyncStatus()
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', updateTableMaxHeight)
  stopPaymentPolling()
})
</script>

<style scoped>
.st-page { max-width: 1780px; margin: 0 auto; padding: 16px 22px 0; }
.st-hero { display: flex; justify-content: space-between; gap: 20px; align-items: center; margin-bottom: 8px; }
.st-hero-main { display: flex; align-items: center; gap: 10px; min-width: 0; }
.st-title { margin: 0; font-size: 20px; color: #172554; }
.st-subtitle { display: flex; align-items: center; gap: 8px; color: #64748b; font-size: 12px; }
.st-hero-actions { display: flex; gap: 8px; }
.st-tabs { margin-top: 0; }
.st-tabs :deep(.el-tabs__header) { margin: 0 0 10px; }
.st-tabs :deep(.el-tabs__item) { height: 32px; line-height: 32px; }
.st-filter-panel { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 10px 14px; margin-bottom: 12px; background: #fff; border: 1px solid #e5eaf2; border-radius: 10px; }
.st-summary-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
.st-summary-card { background: #fff; border: 1px solid #e5eaf2; border-radius: 10px; padding: 10px 14px; box-shadow: 0 3px 10px rgba(30, 64, 175, 0.04); min-width: 0; }
.st-summary-card span { display: block; font-size: 12px; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.st-summary-card strong { display: block; font-size: 20px; line-height: 1.25; margin: 0; color: #1e293b; }
.st-summary-card small { display: none; }
.st-summary-card.is-green { border-top: 3px solid #22c55e; }
.st-summary-card.is-blue { border-top: 3px solid #3b82f6; }
.st-summary-card.is-red { border-top: 3px solid #ef4444; }
.st-summary-card.is-gray { border-top: 3px solid #94a3b8; }
.st-summary-card.is-cyan { border-top: 3px solid #06b6d4; }
.st-summary-card.is-amber { border-top: 3px solid #f59e0b; }
.st-panel { background: #fff; border: 1px solid #e5eaf2; border-radius: 10px; padding: 12px; box-shadow: 0 5px 18px rgba(30, 64, 175, 0.05); }
.st-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.st-panel-title { font-size: 15px; font-weight: 700; color: #1e293b; }
.st-count { margin-left: 10px; font-size: 12px; color: #94a3b8; }
.st-booking-note { margin-left: 12px; font-size: 12px; color: #94a3b8; }
.st-selected { margin-left: 14px; font-size: 12px; color: #2563eb; font-weight: 700; }
.st-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.st-pager { margin-top: 8px; padding: 8px 0 2px; justify-content: flex-end; background: #fff; }
.st-column-settings { display: flex; flex-direction: column; gap: 6px; }
.st-column-title { font-size: 12px; color: #64748b; margin-bottom: 2px; }
.st-column-settings .el-checkbox { margin-right: 0; height: 28px; }
.st-detail-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.st-detail-ladder { font-size: 16px; font-weight: 700; color: #172554; }
.st-detail-module { margin-top: 4px; font-size: 12px; color: #64748b; }
.st-detail-section-title { margin: 18px 0 8px; font-size: 14px; font-weight: 700; color: #1e293b; }
.st-daily-note { display: flex; align-items: center; gap: 8px; padding: 12px 14px; margin-bottom: 14px; border-radius: 10px; background: #eff6ff; color: #1d4ed8; font-size: 13px; }
.st-daily-toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 14px; margin-bottom: 14px; border-radius: 10px; background: #f8fafc; border: 1px dashed #cbd5e1; }
.st-toolbar-label { font-size: 13px; font-weight: 700; color: #475569; }
.st-hint { font-size: 12px; color: #94a3b8; }
.st-import-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.st-import-card { background: #fff; border: 1px solid #e5eaf2; border-radius: 12px; padding: 18px; box-shadow: 0 5px 18px rgba(30, 64, 175, 0.05); }
.st-import-title { font-size: 17px; font-weight: 700; color: #1e293b; }
.st-import-desc { min-height: 54px; margin: 8px 0 14px; color: #64748b; font-size: 13px; line-height: 1.65; }
.st-import-form { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.st-file-name { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: #64748b; }
.st-import-foot { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 14px; padding-top: 12px; border-top: 1px solid #f1f5f9; font-size: 12px; color: #94a3b8; }
.st-sync-card { margin-bottom: 16px; }
.st-sync-status { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 8px; font-size: 12px; color: #475569; }
.st-sync-stats { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 12px; font-size: 12px; color: #64748b; }
.st-dialog-form { margin-top: 16px; }
.st-dialog-summary { padding: 10px 12px; border-radius: 8px; background: #f8fafc; color: #475569; font-size: 13px; }
.st-history-head { margin-bottom: 12px; color: #1d4ed8; font-size: 15px; font-weight: 700; }
.st-preview-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; font-size: 12px; color: #64748b; }
.st-column-map { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 10px; }
.st-column-map-title { font-size: 12px; color: #64748b; margin-right: 2px; }
.st-status-line { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
.st-status-chip { padding: 5px 10px; border-radius: 999px; background: #f1f5f9; color: #475569; font-size: 12px; }
.st-payment-panel { margin-bottom: 16px; }
.st-payment-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.st-payment-head .st-import-desc { min-height: 0; margin-bottom: 0; }
.st-payment-file-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.st-payment-file-card { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 14px; border: 1px solid #e2e8f0; border-radius: 10px; background: #f8fafc; }
.st-payment-file-title { display: flex; justify-content: space-between; align-items: center; gap: 10px; width: 100%; font-size: 14px; font-weight: 700; color: #1e293b; }
.st-payment-file-hint { min-height: 34px; margin: 0; color: #64748b; font-size: 12px; line-height: 1.5; }
.st-payment-file-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; min-height: 18px; color: #64748b; font-size: 12px; }
.st-payment-file-meta.is-empty { color: #94a3b8; }
.st-payment-filename { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-payment-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 16px; padding-top: 14px; border-top: 1px solid #f1f5f9; }
.st-payment-note { color: #94a3b8; font-size: 12px; }
.st-payment-run-title { color: #64748b; font-size: 12px; }
.st-payment-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.st-payment-stats > div { padding: 10px 12px; border-radius: 8px; background: #f8fafc; }
.st-payment-stats span { display: block; margin-bottom: 4px; color: #64748b; font-size: 12px; }
.st-payment-stats strong { color: #1e293b; font-size: 15px; }
.st-payment-stats strong.is-danger { color: #dc2626; }
.st-payment-stats strong.is-warning { color: #d97706; }
@media (max-width: 1100px) {
  .st-summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .st-import-grid { grid-template-columns: 1fr; }
  .st-payment-file-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .st-page { padding: 12px; }
  .st-hero { display: block; }
  .st-hero-actions { margin-top: 12px; }
  .st-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .st-payment-head { display: block; }
  .st-payment-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
