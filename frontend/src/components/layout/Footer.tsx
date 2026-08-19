import { BrandLogo } from "@/components/brand/BrandLogo";

const ICP_NUMBER =
  import.meta.env.VITE_ICP_BEIAN_NUMBER || "鄂ICP备2026044084号-1";

export function Footer() {
  return (
    <footer className="border-t border-border/60 py-4 text-center text-xs text-muted-foreground">
      <div className="mb-2 flex justify-center">
        <BrandLogo size="sm" />
      </div>
      <p>© 2026 AgentHub. All rights reserved.</p>
      <p className="mt-1">
        <a
          href="https://beian.miit.gov.cn/"
          target="_blank"
          rel="noopener noreferrer"
          className="transition-colors hover:text-foreground"
        >
          {ICP_NUMBER}
        </a>
      </p>
    </footer>
  );
}
