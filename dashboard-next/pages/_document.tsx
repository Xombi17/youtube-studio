import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" className="dark">
      <Head>
        <meta name="description" content="CreatorRadar — local-first autonomous YouTube clip studio" />
        <meta name="theme-color" content="#0A0C10" />
        <meta name="color-scheme" content="dark" />
      </Head>
      <body className="antialiased">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
