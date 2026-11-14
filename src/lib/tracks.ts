// The six sponsor tracks. The slug is the route (/lenovo), the folder (src/app/lenovo/)
// and the PR title prefix ("lenovo: ..."). Set ready: true when a track meets its done bar;
// the home page and the presenter bar then show it as a finished demo.
export type Track = { slug: string; name: string; channel: number; ready: boolean };

export const tracks: Track[] = [
  { slug: "rtx", name: "RTX", channel: 2, ready: false },
  { slug: "cisco", name: "Cisco", channel: 3, ready: false },
  { slug: "amat", name: "Applied Materials", channel: 4, ready: false },
  { slug: "sandia", name: "Sandia National Laboratories", channel: 5, ready: false },
  { slug: "lenovo", name: "Lenovo", channel: 6, ready: false },
  { slug: "medtronic", name: "Medtronic", channel: 7, ready: false },
];
