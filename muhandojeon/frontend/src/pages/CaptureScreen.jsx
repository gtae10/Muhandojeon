import { useRef, useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { registerFingerprint } from '../api/client.js'

export default function CaptureScreen() {
  const { productId = 'demo' } = useParams()
  const navigate = useNavigate()
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [status, setStatus] = useState('idle') // idle | camera-on | uploading | error

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      })
      streamRef.current = stream
      if (videoRef.current) videoRef.current.srcObject = stream
      setStatus('camera-on')
    } catch {
      setStatus('error')
    }
  }

  async function capture() {
    if (!videoRef.current) return
    const canvas = document.createElement('canvas')
    canvas.width = videoRef.current.videoWidth
    canvas.height = videoRef.current.videoHeight
    canvas.getContext('2d').drawImage(videoRef.current, 0, 0)

    canvas.toBlob(async (blob) => {
      setStatus('uploading')
      try {
        // TODO(AI1 담당): 실제 지문/마모도 분석 붙으면 응답 처리 로직 추가
        await registerFingerprint(productId, blob)
        navigate(`/product/${productId}`)
      } catch {
        setStatus('error')
      }
    }, 'image/jpeg')
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-medium">제품 텍스처 촬영</h1>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          가죽 결·스티치가 잘 보이도록 가까이서 촬영해주세요
        </p>
      </div>

      <div className="aspect-square rounded-2xl bg-[var(--color-surface)] overflow-hidden flex items-center justify-center">
        {status === 'idle' && (
          <button
            onClick={startCamera}
            className="text-sm px-4 py-2 rounded-full border border-white/20"
          >
            카메라 시작
          </button>
        )}
        {status === 'error' && (
          <p className="text-sm text-red-400 px-6 text-center">
            카메라 접근에 실패했습니다. 권한을 확인해주세요.
          </p>
        )}
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`w-full h-full object-cover ${
            status === 'camera-on' || status === 'uploading' ? 'block' : 'hidden'
          }`}
        />
      </div>

      {(status === 'camera-on' || status === 'uploading') && (
        <button
          onClick={capture}
          disabled={status === 'uploading'}
          className="w-full py-3 rounded-full bg-[var(--color-accent)] text-black text-sm disabled:opacity-50"
        >
          {status === 'uploading' ? '등록 중…' : '촬영하고 등록'}
        </button>
      )}
    </div>
  )
}
