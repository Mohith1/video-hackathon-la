"use client";
import { useTheme } from "./ThemeProvider";

export default function NavBar() {
  const { theme, toggle } = useTheme();

  return (
    <nav
      className="border-b px-6 py-3 flex items-center gap-3 sticky top-0 z-50 backdrop-blur-sm"
      style={{ borderColor: "var(--border)", backgroundColor: "color-mix(in srgb, var(--bg) 85%, transparent)" }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2 mr-2">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-teal-400 to-teal-600 flex items-center justify-center shadow-lg">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1" y="4" width="2" height="6" rx="1" fill="white" opacity="0.7"/>
            <rect x="4.5" y="2" width="2" height="10" rx="1" fill="white"/>
            <rect x="8" y="5" width="2" height="5" rx="1" fill="white" opacity="0.7"/>
            <rect x="11.5" y="3" width="2" height="7" rx="1" fill="white" opacity="0.5"/>
          </svg>
        </div>
        <span className="font-bold text-base tracking-tight" style={{ color: "var(--text)" }}>
          Narrative <span className="text-teal-500">AI</span>
        </span>
      </div>

      <span className="text-xs" style={{ color: "var(--border)" }}>|</span>
      <span className="text-xs hidden sm:block" style={{ color: "var(--text-3)" }}>
        Intelligent Video Segmentation · TwelveLabs + AWS Bedrock
      </span>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Theme toggle */}
      <button
        onClick={toggle}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        className="w-9 h-9 rounded-lg flex items-center justify-center transition-all hover:scale-105"
        style={{ backgroundColor: "var(--bg-subtle)", color: "var(--text-2)" }}
      >
        {theme === "dark" ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="4"/>
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        )}
      </button>
    </nav>
  );
}
