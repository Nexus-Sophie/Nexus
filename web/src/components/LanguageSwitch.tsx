import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export function LanguageSwitch() {
  const { i18n, t } = useTranslation();
  const isEnglish = i18n.resolvedLanguage === 'en';
  const nextLanguage = isEnglish ? 'zh' : 'en';

  const handleToggle = () => {
    void i18n.changeLanguage(nextLanguage);
  };

  return (
    <div className="flex items-center gap-2" aria-label={t('language.label')}>
      <span className="hidden text-xs font-medium text-slate-500 dark:text-slate-400 sm:inline">
        {t('language.zh')}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={isEnglish}
        aria-label={t('language.switchTo', { language: t(`language.${nextLanguage}`) })}
        onClick={handleToggle}
        className={cn(
          'relative inline-flex h-7 w-14 shrink-0 items-center rounded-full border border-slate-200 bg-slate-100 p-0.5 shadow-sm transition-colors duration-200',
          'hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2',
          'dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700',
          isEnglish && 'bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600'
        )}
      >
        <span
          className={cn(
            'inline-flex h-6 w-6 items-center justify-center rounded-full bg-white text-[10px] font-semibold text-slate-700 shadow-sm transition-transform duration-200',
            isEnglish ? 'translate-x-7' : 'translate-x-0'
          )}
        >
          {isEnglish ? 'EN' : '中'}
        </span>
      </button>
      <span className="hidden text-xs font-medium text-slate-500 dark:text-slate-400 sm:inline">
        {t('language.en')}
      </span>
    </div>
  );
}
