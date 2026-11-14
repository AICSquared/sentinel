import type { Metadata } from "next";
import { Closing, Decide, Hero } from "./_site/home-sections";
import { SpreadStory } from "./_site/spread-story";
import { buildStory } from "./_site/story";

// Home: one scroll that tells the recorded run. (a) the team at rest, (b) the drawing pins while one
// agent turns and the spread is traced, (c) Sentinel recommends, a person decides, (d) close.
// Everything comes from the recorded run, so it works offline with no keys.
export const metadata: Metadata = { title: { absolute: "Sentinel" } };

export default function Home() {
  const story = buildStory();
  return (
    <main>
      <Hero story={story} />
      <SpreadStory story={story} />
      <Decide story={story} />
      <Closing story={story} />
    </main>
  );
}
