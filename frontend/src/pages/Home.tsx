import React, { useState, useEffect } from 'react'
import { Upload, Table, Tag, Button, message, Progress } from 'antd'
import { InboxOutlined, EyeOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { getExams, uploadExam } from '../api'
import type { Exam } from '../types'
import { usePolling } from '../hooks/usePolling'
import { useAuth } from '../hooks/useAuth'

const { Dragger } = Upload

const Home: React.FC = () => {
  const navigate = useNavigate()
  const { requireAuth } = useAuth()
  const [exams, setExams] = useState<Exam[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)

  useEffect(() => {
    requireAuth()
  }, [requireAuth])

  const fetchExams = async () => {
    try {
      const data = await getExams(1, 50)
      setExams(data.items)
    } catch (error) {
      console.error('Failed to fetch exams:', error)
    } finally {
      setLoading(false)
    }
  }

  const hasProcessingExams = exams.some(e => e.status === 'pending' || e.status === 'processing')
  
  usePolling(fetchExams, hasProcessingExams ? 3000 : null, true)

  const handleCustomRequest = async (options: any) => {
    const { file, onSuccess, onError } = options
    
    setUploading(true)
    setUploadProgress(0)
    
    try {
      const fakeProgress = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 90) {
            clearInterval(fakeProgress)
            return 90
          }
          return prev + 10
        })
      }, 500)

      const exam = await uploadExam(file as File)
      
      clearInterval(fakeProgress)
      setUploadProgress(100)
      
      message.success('视频上传成功，开始分析')
      onSuccess(exam, file)
      
      setTimeout(() => {
        setUploading(false)
        navigate(`/exam/${exam.id}`)
      }, 1000)
    } catch (error) {
      console.error('Upload failed:', error)
      message.error('视频上传失败')
      onError(error)
      setUploading(false)
    }
  }

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'completed': return <Tag color="success">已完成</Tag>
      case 'processing': return <Tag color="processing" className="animate-pulse">分析中</Tag>
      case 'pending': return <Tag color="default">等待中</Tag>
      case 'failed': return <Tag color="error">失败</Tag>
      default: return <Tag>{status}</Tag>
    }
  }

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text: string) => new Date(text).toLocaleString('zh-CN'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '总分',
      dataIndex: 'total_score',
      key: 'total_score',
      render: (score: number | null, record: Exam) => {
        if (record.status !== 'completed') return '-'
        const color = score && score >= 80 ? 'text-green-600' : score && score >= 60 ? 'text-yellow-600' : 'text-red-600'
        return <span className={`font-bold ${color}`}>{score}</span>
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Exam) => (
        <Button 
          type="link" 
          icon={<EyeOutlined />} 
          onClick={() => navigate(`/exam/${record.id}`)}
        >
          查看详情
        </Button>
      ),
    },
  ]

  return (
    <div className="space-y-8">
      <div className="bg-blue-50 p-8 rounded-xl border border-blue-100">
        <h2 className="text-2xl font-bold text-blue-800 mb-2">上传急救操作视频</h2>
        <p className="text-blue-600 mb-6">支持 .mp4, .mov, .avi 格式，系统将自动进行多模态AI评分</p>
        
        <Dragger 
          customRequest={handleCustomRequest}
          showUploadList={false}
          accept="video/mp4,video/quicktime,video/x-msvideo"
          disabled={uploading}
          className="bg-white"
        >
          {uploading ? (
            <div className="py-8">
              <Progress type="circle" percent={uploadProgress} />
              <p className="mt-4 text-gray-500">正在上传并处理视频...</p>
            </div>
          ) : (
            <div className="py-8">
              <p className="ant-upload-drag-icon">
                <InboxOutlined className="text-blue-500" />
              </p>
              <p className="ant-upload-text text-lg font-medium">点击或拖拽视频文件到此区域上传</p>
              <p className="ant-upload-hint text-gray-400 mt-2">
                单次仅支持上传一个视频文件
              </p>
            </div>
          )}
        </Dragger>
      </div>

      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-800">历史考核记录</h2>
          <Button onClick={fetchExams} loading={loading}>刷新</Button>
        </div>
        
        <Table 
          columns={columns} 
          dataSource={exams} 
          rowKey="id" 
          loading={loading}
          pagination={{ pageSize: 10 }}
          className="border border-gray-100 rounded-lg overflow-hidden"
        />
      </div>
    </div>
  )
}

export default Home
