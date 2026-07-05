import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

// Thin ECharts wrapper: give it an `option` object and a height. It creates
// one chart instance, updates it when the option changes, and resizes with
// the window. Kept tiny on purpose so every dashboard chart is one <Chart/>.
export default function Chart({ option, height = 220, style }) {
  const ref = useRef(null)
  const inst = useRef(null)

  useEffect(() => {
    inst.current = echarts.init(ref.current)
    const onResize = () => inst.current && inst.current.resize()
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); inst.current && inst.current.dispose() }
  }, [])

  useEffect(() => {
    if (inst.current && option) inst.current.setOption(option, true)
  }, [option])

  return <div ref={ref} style={{ width: '100%', height, ...style }} />
}
