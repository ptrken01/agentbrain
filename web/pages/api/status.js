import { NextApiRequest, NextApiResponse } from 'next'

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  res.status(200).json({
    name: 'AgentBrain',
    version: '1.0.0',
    status: 'live',
    mcp_endpoint: 'https://agentbrain.autoincomesys.com/mcp',
    api_endpoint: 'https://agentbrain.autoincomesys.com/api',
    tools: [
      'remember',
      'recall',
      'register_agent',
      'discover_agents',
      'add_knowledge',
      'query_knowledge',
      'get_context'
    ],
    stats: {
      agents_registered: 0,
      memories_stored: 0,
      knowledge_nodes: 0
    }
  })
}
