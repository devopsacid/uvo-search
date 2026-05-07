import { useParams, useNavigate } from 'react-router-dom'
import { EgoNetwork } from '@/components/graph/EgoNetwork'

export function FirmaSietTab() {
  const { ico } = useParams<{ ico: string }>()
  const navigate = useNavigate()
  const safeIco = ico ?? ''

  return (
    <div className="py-4">
      <EgoNetwork
        ico={safeIco}
        hops={2}
        height="500px"
        onNodeClick={(nodeIco) => navigate('/firma/' + nodeIco)}
      />
    </div>
  )
}
