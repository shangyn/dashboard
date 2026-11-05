import { nextTick, onBeforeUnmount, onMounted } from 'vue'

/**
 * 个别 Chrome 环境在内部滚动的 el-table 上会出现「新滚出来的行只绘制了部分单元格」
 * 的重绘缺陷（数据与 DOM 都在，只是没画出来）。滚动停止后对表格主体做一次两帧的
 * 恒等 transform，强制浏览器重建该层，视觉上无变化，可恢复正常绘制。
 */
export function useTableRepaint(getTable) {
  let timer = null
  let wrap = null
  let stopped = false

  function root() {
    const el = typeof getTable === 'function' ? getTable() : getTable?.value
    return el && (el.$el || el)
  }

  function nudge() {
    if (stopped) return
    const el = typeof getTable === 'function' ? getTable() : getTable?.value
    if (el && typeof el.doLayout === 'function') el.doLayout()
    const body = root()?.querySelector('.el-table__body')
    if (!body) return
    body.style.transform = 'translateZ(0)'
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!stopped) body.style.transform = ''
      })
    })
  }

  function schedule() {
    clearTimeout(timer)
    timer = setTimeout(nudge, 80)
  }

  onMounted(async () => {
    await nextTick()
    wrap = root()?.querySelector('.el-scrollbar__wrap') || null
    wrap?.addEventListener('scroll', schedule, { passive: true })
  })

  onBeforeUnmount(() => {
    stopped = true
    clearTimeout(timer)
    wrap?.removeEventListener('scroll', schedule)
    wrap = null
  })

  return { nudge }
}
