import Head from 'next/head'
import { Brain, ArrowRight, Calendar } from 'lucide-react'

const posts = [
  {
    slug: 'why-every-ai-agent-needs-a-shared-brain',
    title: 'Why Every AI Agent Needs a Shared Brain',
    date: '2026-08-16',
    excerpt: 'Every AI agent today starts from scratch. Zero memory. Zero context. This is the biggest waste in AI — and the biggest opportunity.',
    category: 'Thesis'
  },
  {
    slug: 'context-beats-intelligence',
    title: 'Context Beats Intelligence: The Flo Crivello Insight',
    date: '2026-08-16',
    excerpt: 'An agent with 100K tokens of context beats Einstein without context. Why the shared context layer is the most valuable infrastructure in AI.',
    category: 'Insights'
  },
  {
    slug: 'mcp-is-winning-what-comes-next',
    title: 'MCP Is Winning. What Comes Next?',
    date: '2026-08-16',
    excerpt: 'The Model Context Protocol is becoming the standard for agent-to-tool communication. But the missing piece is the shared brain.',
    category: 'Analysis'
  },
  {
    slug: 'the-agent-economy-is-coming',
    title: 'The Agent Economy Is Coming. Are You Ready?',
    date: '2026-08-16',
    excerpt: 'Agents will soon outnumber humans online. They will need to discover each other, build trust, and transact. AgentBrain provides the infrastructure.',
    category: 'Vision'
  },
  {
    slug: 'how-to-build-an-mcp-server',
    title: 'How to Build an MCP Server: Complete Guide',
    date: '2026-08-16',
    excerpt: 'A step-by-step guide to building your own MCP server. Connect any AI agent to your tools and data.',
    category: 'Tutorial'
  },
  {
    slug: 'agentmesh-vs-agentbrain',
    title: 'AgentMesh vs AgentBrain: What's the Difference?',
    date: '2026-08-16',
    excerpt: 'AgentMesh provides agent networking. AgentBrain provides the shared brain. They are complementary — and together they form the full agent stack.',
    category: 'Comparison'
  }
]

export default function Blog() {
  return (
    <>
      <Head>
        <title>Blog — AgentBrain</title>
        <meta name="description" content="AgentBrain blog: insights on AI agents, shared context, MCP, and the agent economy." />
        <meta property="og:title" content="Blog — AgentBrain" />
        <meta property="og:description" content="Insights on AI agents, shared context, MCP, and the agent economy." />
      </Head>

      <div className="min-h-screen bg-slate-950 pt-20">
        <div className="max-w-4xl mx-auto px-4 py-12">
          <div className="mb-12">
            <h1 className="text-4xl font-bold mb-4">Blog</h1>
            <p className="text-xl text-slate-400">Insights on AI agents, shared context, and the agent economy.</p>
          </div>

          <div className="space-y-6">
            {posts.map((post) => (
              <article key={post.slug} className="card p-8 hover:border-brand-700/50 transition">
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-xs bg-brand-900/50 text-brand-300 px-2 py-1 rounded-full">{post.category}</span>
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Calendar className="w-3 h-3" /> {post.date}
                  </span>
                </div>
                <h2 className="text-xl font-semibold mb-2">{post.title}</h2>
                <p className="text-slate-400 mb-4">{post.excerpt}</p>
                <a href={`/blog/${post.slug}`} className="text-brand-400 hover:text-brand-300 text-sm font-medium flex items-center gap-1">
                  Read more <ArrowRight className="w-4 h-4" />
                </a>
              </article>
            ))}
          </div>
        </div>
      </div>

      <footer className="border-t border-slate-800 py-8 px-4">
        <div className="max-w-4xl mx-auto text-center text-sm text-slate-500">
          <p>&copy; 2026 AgentBrain. <a href="/" className="text-brand-400 hover:text-brand-300">Home</a> · <a href="/docs" className="text-brand-400 hover:text-brand-300">Docs</a></p>
        </div>
      </footer>
    </>
  )
}
