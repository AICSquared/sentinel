// The tracks this portal shows. The slug is the route (/sentinel), the folder (src/app/sentinel/)
// and the PR title prefix ("sentinel: ..."). Set ready: true when a track meets its done bar;
// the presenter bar then shows it as a finished demo.
export type Track = { slug: string; name: string; channel: number; ready: boolean };

export const tracks: Track[] = [
  // This repo builds one track: Sentinel, for Cisco's Mission 3. Board channel #2.
  { slug: "sentinel", name: "Sentinel", channel: 2, ready: false },
];
