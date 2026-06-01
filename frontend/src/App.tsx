import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Layout from './components/Layout'
import Home from './pages/Home'
import ExamDetail from './pages/ExamDetail'
import Report from './pages/Report'
// 临时去除登录注册：保留 Login 组件以便后续恢复，仅暂停其路由

const App: React.FC = () => {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          {/* 临时去除登录注册：/login 直接重定向到首页 */}
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/" element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="exam/:id" element={<ExamDetail />} />
            <Route path="exam/:id/report" element={<Report />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
