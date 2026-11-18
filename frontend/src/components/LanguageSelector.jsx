import { useTranslation } from "../i18n";

export default function LanguageSelector({ className = "" }) {
  const { lang, setLang } = useTranslation();

  return (
    <div className={className}>
      <select
        value={lang}
        onChange={(e) => setLang(e.target.value)}
        aria-label="Language"
        className="min-h-10 rounded-xl border border-slate-200 bg-white/90 px-3 text-sm font-bold text-slate-700 shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-violet-500"
      >
        <option value="en">English</option>
        <option value="si">සිංහල</option>
      </select>
    </div>
  );
}
