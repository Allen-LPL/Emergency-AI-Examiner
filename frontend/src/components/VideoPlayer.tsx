import React, { useEffect, useRef, useState } from 'react'
import { Button, Slider } from 'antd'
import { PlayCircleOutlined, PauseCircleOutlined } from '@ant-design/icons'

interface VideoPlayerProps {
  src: string
  currentTime?: number
  onTimeUpdate?: (time: number) => void
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({ src, currentTime, onTimeUpdate }) => {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [current, setCurrent] = useState(0)

  useEffect(() => {
    if (videoRef.current && currentTime !== undefined && Math.abs(videoRef.current.currentTime - currentTime) > 0.5) {
      videoRef.current.currentTime = currentTime
    }
  }, [currentTime])

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrent(videoRef.current.currentTime)
      if (onTimeUpdate) {
        onTimeUpdate(videoRef.current.currentTime)
      }
    }
  }

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration)
    }
  }

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause()
      } else {
        videoRef.current.play()
      }
      setIsPlaying(!isPlaying)
    }
  }

  const handleSliderChange = (value: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = value
      setCurrent(value)
    }
  }

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className="video-container flex flex-col">
      <video
        ref={videoRef}
        src={src}
        className="w-full h-auto max-h-[60vh] object-contain bg-black"
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onClick={togglePlay}
      />
      
      <div className="bg-gray-900 p-4 flex items-center gap-4 text-white">
        <Button 
          type="text" 
          className="text-white hover:text-blue-400"
          icon={isPlaying ? <PauseCircleOutlined className="text-2xl" /> : <PlayCircleOutlined className="text-2xl" />}
          onClick={togglePlay}
        />
        
        <span className="text-sm font-mono w-12 text-right">{formatTime(current)}</span>
        
        <Slider
          className="flex-1 mx-4"
          min={0}
          max={duration || 100}
          value={current}
          onChange={handleSliderChange}
          tooltip={{ formatter: (val) => formatTime(val || 0) }}
        />
        
        <span className="text-sm font-mono w-12">{formatTime(duration)}</span>
      </div>
    </div>
  )
}

export default VideoPlayer
