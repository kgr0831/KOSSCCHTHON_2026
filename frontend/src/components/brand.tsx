import Link from "next/link";

export function Brand() {
  return <Link href="/" className="brand" aria-label="두드리 홈"><img src="/figma/logo.png" alt="" width="36" height="36" /><span>두드리</span></Link>;
}

export function Mascot() {
  return <div className="mascot" role="img" aria-label="반갑게 인사하는 두드리 캐릭터"><img src="/figma/mascot-sheet.png" alt="" width="1536" height="1024" /></div>;
}
