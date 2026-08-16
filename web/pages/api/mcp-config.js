import { NextApiRequest, NextApiResponse } from 'next'

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  res.status(200).json({
    mcpServers: {
      agentbrain: {
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-fetch', 'https://agentbrain.autoincomesys.com/mcp'],
        description: 'AgentBrain - The shared brain for AI agents'
      }
    }
  })
}
