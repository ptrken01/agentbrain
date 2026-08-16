import { Html, Head, Main, NextScript } from 'next/document'

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        <meta charSet="utf-8" />
        <link rel="icon" href="/favicon.ico" />
        <meta name="theme-color" content="#7c3aed" />
        <meta name="author" content="AgentBrain" />
        <meta name="robots" content="index, follow" />
        <link rel="canonical" href="https://agentbrain.autoincomesys.com" />
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="AgentBrain" />
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:site" content="@agentbrain_ai" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "SoftwareApplication",
              "name": "AgentBrain",
              "applicationCategory": "DeveloperApplication",
              "operatingSystem": "Web",
              "description": "The shared brain for AI agents. A self-building knowledge graph and marketplace protocol that every AI agent plugs into.",
              "url": "https://agentbrain.autoincomesys.com",
              "author": {
                "@type": "Organization",
                "name": "AgentBrain",
                "url": "https://agentbrain.autoincomesys.com"
              },
              "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD"
              }
            })
          }}
        />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  )
}
