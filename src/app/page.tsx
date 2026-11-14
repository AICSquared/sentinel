import type { Metadata } from "next";
import Link from "next/link";
import { ScrollFlow } from "./_site/scroll-flow";
import { Closing, Decide, Hero, primaryLink } from "./_site/home-sections";
import { buildStory } from "./_site/story";

// Home: one scroll that tells the recorded run. (a) the team at rest, (b) the incident as one timeline that
// plays once on arrival: one agent turns and the spread is traced, (c) Sentinel recommends, a person decides,
// (d) close. Everything comes from the recorded run, so it works offline with no keys.
export const metadata: Metadata = { title: { absolute: "Sentinel" } };

export default function Home() {
  const story = buildStory();
  return (
    <main>
      <Hero story={story} />
      <ScrollFlow story={story}>
        <Link href="/sentinel" className={primaryLink}>Open the explorer</Link>
      </ScrollFlow>
      <Decide story={story} />
      <Closing story={story} />
    </main>
  );
}
