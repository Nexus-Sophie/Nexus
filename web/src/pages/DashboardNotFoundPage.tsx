import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Home, MapPinned } from 'lucide-react';
import { DEFAULT_WORKSPACE_PATH } from '@/lib/dashboard-nav';
import { useAppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';

export function DashboardNotFoundPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  useAppLayout({
    title: t('notFound.pageTitle'),
    description: t('notFound.pageDescription'),
    mainClassName: 'justify-center',
  });

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col items-center rounded-2xl border bg-card/85 px-6 py-12 text-center shadow-sm sm:px-10">
      <div className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <MapPinned className="size-7" aria-hidden="true" />
      </div>

      <p className="mb-3 text-sm font-medium uppercase tracking-[0.2em] text-muted-foreground">
        {t('notFound.eyebrow')}
      </p>
      <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        {t('notFound.heading')}
      </h2>
      <p className="mt-4 max-w-xl text-base leading-7 text-muted-foreground">
        {t('notFound.body')}
      </p>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Button asChild size="lg">
          <Link to={DEFAULT_WORKSPACE_PATH}>
            <Home className="size-4" aria-hidden="true" />
            {t('notFound.taskBoardAction')}
          </Link>
        </Button>
        <Button type="button" variant="outline" size="lg" onClick={() => navigate(-1)}>
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t('notFound.backAction')}
        </Button>
      </div>
    </section>
  );
}
