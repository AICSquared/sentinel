import { redirect } from "next/navigation";

// The portal is Sentinel only: the home page goes straight to it.
export default function Home() {
  redirect("/sentinel");
}
