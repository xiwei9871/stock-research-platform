import { IndustryCatalogWorkspace } from './IndustryCatalogWorkspace';
import { ThemeResearchWorkspace } from './ThemeResearchWorkspace';

type ThemeResearchAndIndustryCatalogWorkspaceProps = {
  pathname: string;
  onNavigate: (path: string) => void;
  onOpenStock: (path: string) => void;
};

export function ThemeResearchAndIndustryCatalogWorkspace({
  pathname,
  onNavigate,
  onOpenStock
}: ThemeResearchAndIndustryCatalogWorkspaceProps) {
  const catalogRoute = pathname === '/theme-research/catalog' || pathname.startsWith('/theme-research/catalog/');

  return (
    <section className="theme-research-workspace" aria-label="主题研究与产业目录工作台">
      <nav className="theme-research-tabs" aria-label="主题研究与产业目录视图">
        <button
          type="button"
          aria-current={!catalogRoute ? 'page' : undefined}
          onClick={() => onNavigate('/theme-research')}
        >
          主题研究
        </button>
        <button
          type="button"
          aria-current={catalogRoute ? 'page' : undefined}
          onClick={() => onNavigate('/theme-research/catalog')}
        >
          产业目录
        </button>
      </nav>
      {catalogRoute ? (
        <IndustryCatalogWorkspace pathname={pathname} onNavigate={onNavigate} />
      ) : (
        <ThemeResearchWorkspace pathname={pathname} onNavigate={onNavigate} onOpenStock={onOpenStock} />
      )}
    </section>
  );
}
