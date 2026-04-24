import { useEffect, useRef } from 'react'

export const usePolling = (
  callback: () => void,
  interval: number | null,
  immediate = true
) => {
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (interval === null) {
      return
    }

    if (immediate) {
      savedCallback.current()
    }

    const id = setInterval(() => savedCallback.current(), interval)
    return () => clearInterval(id)
  }, [interval, immediate])
}
