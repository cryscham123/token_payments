"use client";

import { useEffect, useState, useRef } from "react";
import { Loader2 } from "lucide-react";
import { apiJson } from "@/lib/auth-client";



export default function UserSearchInput({ value, onChange, onSelectUser, placeholder }) {
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const dropdownRef = useRef(null);

  // Debounced Search Effect
  useEffect(() => {
    if (!value.trim()) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }

    setSearchLoading(true);
    const delayDebounceFn = setTimeout(async () => {
      try {
        const res = await apiJson(`/merchant/users/search?query=${encodeURIComponent(value.trim())}`);
        if (res?.users) {
          setSearchResults(res.users);
        }
      } catch (err) {
        console.error("Search failed:", err);
      } finally {
        setSearchLoading(false);
      }
    }, 250);

    return () => clearTimeout(delayDebounceFn);
  }, [value]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false);
        setActiveSuggestionIndex(-1);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectUserCandidate = (user) => {
    onSelectUser(user);
    onChange(user.displayName || user.walletAddress);
    setShowDropdown(false);
    setActiveSuggestionIndex(-1);
  };

  const handleKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (searchResults.length === 0) return;
      setActiveSuggestionIndex(prev => 
        prev < searchResults.length - 1 ? prev + 1 : 0
      );
      setShowDropdown(true);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (searchResults.length === 0) return;
      setActiveSuggestionIndex(prev => 
        prev > 0 ? prev - 1 : searchResults.length - 1
      );
      setShowDropdown(true);
    } else if (e.key === "Enter") {
      if (showDropdown && activeSuggestionIndex >= 0 && activeSuggestionIndex < searchResults.length) {
        e.preventDefault();
        const user = searchResults[activeSuggestionIndex];
        selectUserCandidate(user);
      }
    } else if (e.key === "Escape") {
      setShowDropdown(false);
      setActiveSuggestionIndex(-1);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <input
        id="invite-search"
        type="text"
        autoComplete="off"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setShowDropdown(true);
        }}
        onFocus={() => {
          if (value.trim()) {
            setShowDropdown(true);
          }
        }}
        onKeyDown={handleKeyDown}
        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all hover:border-slate-300"
        placeholder={placeholder}
      />
      
      {/* Dropdown Popover */}
      {showDropdown && value.trim() && (
        <div className="absolute left-0 right-0 mt-1 max-h-60 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl z-50 divide-y divide-slate-100">
          {searchLoading && searchResults.length === 0 ? (
            <div className="p-3 text-xs text-slate-400 flex items-center justify-center gap-1.5">
              <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
              <span>유저 검색 중...</span>
            </div>
          ) : searchResults.length === 0 ? (
            <div className="p-3 text-xs text-slate-400 text-center font-medium">
              일치하는 후보가 없습니다.
            </div>
          ) : (
            searchResults.map((user, idx) => {
              const isHighlighted = idx === activeSuggestionIndex;
              return (
                <div
                  key={user.userId}
                  onMouseEnter={() => setActiveSuggestionIndex(idx)}
                  onClick={() => selectUserCandidate(user)}
                  className={`p-3 text-xs text-left cursor-pointer transition-colors duration-150 flex flex-col gap-0.5 ${
                    isHighlighted ? "bg-blue-50 text-blue-900 font-bold" : "text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <span className="font-bold text-slate-900">
                    {user.displayName || "이름 없음"}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {user.walletAddress}
                  </span>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
