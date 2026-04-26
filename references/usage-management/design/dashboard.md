<!DOCTYPE html>

<html class="" lang="en" style=""><head></head><body class="bg-background text-on-surface antialiased min-h-screen flex flex-col md:flex-row"><svg aria-hidden="true" class="inline-defs-container" style="position:absolute;width:0;height:0;overflow:hidden"></svg>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Glacier AI - Credit Manager Dashboard</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script id="tailwind-config">tailwind.config = {theme: {extend: {colors: {background: "#fcf8ff", "on-surface": "#1b1b24", "on-surface-variant": "#464555", primary: "#3525cd", "surface-container-high": "#eae6f4", "outline-variant": "#c7c4d8", tertiary: "#7e3000", secondary: "#565e74", "on-background": "#1b1b24", "inverse-primary": "#c3c0ff", "on-error": "#ffffff", "inverse-surface": "#302f39", "primary-fixed-dim": "#c3c0ff", "on-secondary-container": "#5c647a", "on-primary-fixed-variant": "#3323cc", "surface-bright": "#fcf8ff", "tertiary-fixed": "#ffdbcc", "on-primary": "#ffffff", "on-secondary-fixed": "#131b2e", "on-secondary-fixed-variant": "#3f465c", surface: "#fcf8ff", "surface-dim": "#dcd8e5", "primary-container": "#4f46e5", "on-tertiary": "#ffffff", "surface-tint": "#4d44e3", "primary-fixed": "#e2dfff", "inverse-on-surface": "#f3effc", "tertiary-container": "#a44100", "on-error-container": "#93000a", "surface-variant": "#e4e1ee", "on-tertiary-container": "#ffd2be", "secondary-fixed": "#dae2fd", outline: "#777587", "on-primary-fixed": "#0f0069", "on-tertiary-fixed": "#351000", "surface-container-highest": "#e4e1ee", "secondary-container": "#dae2fd", "surface-container-low": "#f5f2ff", "tertiary-fixed-dim": "#ffb695", "on-tertiary-fixed-variant": "#7b2f00", "on-secondary": "#ffffff", "on-primary-container": "#dad7ff", "error-container": "#ffdad6", "surface-container": "#f0ecf9", "surface-container-lowest": "#ffffff", "secondary-fixed-dim": "#bec6e0", error: "#ba1a1a"}, borderRadius: {DEFAULT: "0.25rem", lg: "0.5rem", xl: "0.75rem", full: "9999px"}, fontFamily: {headline: ["Inter"], display: ["Inter"], body: ["Inter"], label: ["Inter"], "mono-label": ["Inter"], "body-base": ["Inter"], "body-sm": ["Inter"], "label-caps": ["Inter"], h1: ["Inter"], h2: ["Inter"]}, fontSize: {"mono-label": ["12px", {lineHeight: "1", letterSpacing: "-0.01em", fontWeight: "500"}], "body-base": ["14px", {lineHeight: "1.5", letterSpacing: "0", fontWeight: "400"}], "body-sm": ["13px", {lineHeight: "1.5", letterSpacing: "0", fontWeight: "400"}], display: ["48px", {lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "600"}], "label-caps": ["11px", {lineHeight: "1", letterSpacing: "0.05em", fontWeight: "600"}], h1: ["30px", {lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600"}], h2: ["24px", {lineHeight: "1.3", letterSpacing: "-0.01em", fontWeight: "600"}]}, spacing: {"container-padding": "24px", unit: "4px", gutter: "24px", margin: "32px", "bento-gap": "16px"}}}};</script>
<style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
        }
        .glass-panel {
            background: rgba(255, 255, 255, 0.6);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.8);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
        }
        .glass-panel-elevated {
            background: rgba(255, 255, 255, 0.75);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1px solid rgba(255, 255, 255, 0.9);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.05);
        }
        .material-symbols-outlined {
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        }
        .material-symbols-outlined.fill {
            font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        }
        
        /* Simulating Chart for UI purpose */
        .chart-container {
            position: relative;
            height: 300px;
            width: 100%;
            overflow: hidden;
        }
        .chart-line {
            position: absolute;
            bottom: 20%;
            left: 0;
            width: 100%;
            height: 60%;
            background: linear-gradient(to right, transparent, rgba(14, 165, 233, 0.1) 50%, transparent);
            border-top: 2px solid #0ea5e9;
            border-radius: 50% 50% 0 0 / 100% 100% 0 0;
            filter: drop-shadow(0 0 10px rgba(14, 165, 233, 0.3));
        }
        .chart-grid-x {
            position: absolute;
            bottom: 0;
            width: 100%;
            display: flex;
            justify-content: space-between;
            padding: 0 10px;
            color: #475569;
            font-size: 0.75rem;
        }
    </style>
<!-- TopNavBar (Web & Mobile) -->
<header class="sticky top-0 w-full z-30 flex justify-between items-center px-8 bg-white/40 backdrop-blur-lg border-b border-slate-200/60 h-16 md:hidden">
<div class="hidden text-sky-600" style="">Glacier AI</div>
<div class="flex-1 flex justify-end items-center gap-4">
<span class="material-symbols-outlined text-slate-500 cursor-pointer transition-all hover:text-sky-600" style="">notifications</span>
<span class="material-symbols-outlined text-slate-500 cursor-pointer transition-all hover:text-sky-600" style="">settings</span>
<img alt="User avatar" class="w-8 h-8 rounded-full border border-slate-200" data-alt="professional headshot of a person looking forward against a neutral background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuDzCnLQdy89R9naMneJ16iGkEDEpxMY5o356vuDf6NrqEzIWEWqBvv3nD6Gqlz7C9p9wQgrEQLPKdBLznkv-xbsXXvw1jJG_B89upsVcZrVBTvwqxIHBWbgJTQ-QITWVGqVFUCJL3kEzBPES33kA6wu14hEJ_me6Tn_Wjn-V3sIoI80xEjLA59FcV8-NCPNqaK_klkJOWWWNg_uMutOjYKEISKdCw8t-SRLYAuFS4MhImlUV1fk0bYIsNRxTvRvoV_BhzSKnK_zTGU" style=""/>
</div>
</header>
<!-- SideNavBar (Web) -->
<nav class="hidden md:flex flex-col sticky left-0 top-0 h-screen shrink-0 z-40 w-64 border-r border-slate-200/60 bg-white/60 backdrop-blur-xl shadow-[0_0_30px_rgba(0,0,0,0.02)] font-inter antialiased">
<div class="p-6">
<h1 class="text-xl font-bold tracking-tight text-sky-600" style="">Glacier AI</h1>
<p class="text-xs text-on-surface-variant mt-1" style="">Credit Manager</p>
</div>
<div class="flex-1 px-4 py-2 space-y-2">
<a class="flex items-center gap-3 px-4 py-3 text-sky-600 bg-sky-500/10 rounded-xl active:scale-95 duration-200" href="#" style="">
<span class="material-symbols-outlined fill" style="">dashboard</span>
<span class="font-semibold" style="">Dashboard</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-slate-600 hover:bg-sky-500/5 hover:text-sky-600 transition-colors active:scale-95 duration-200 rounded-xl" href="#" style="">
<span class="material-symbols-outlined" style="">group</span>
<span class="" style="">Directory</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-slate-600 hover:bg-sky-500/5 hover:text-sky-600 transition-colors active:scale-95 duration-200 rounded-xl" href="#" style="">
<span class="material-symbols-outlined" style="">person</span>
<span class="" style="">Profile</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-slate-600 hover:bg-sky-500/5 hover:text-sky-600 transition-colors active:scale-95 duration-200 rounded-xl" href="#" style="">
<span class="material-symbols-outlined" style="">analytics</span>
<span class="" style="">Analytics</span>
</a>
</div>
<div class="p-4 mt-auto">
<button class="w-full py-3 rounded-xl bg-primary/10 text-primary border border-primary/20 font-semibold hover:bg-primary/20 transition-all shadow-[0_4px_10px_rgba(14,165,233,0.1)] active:scale-95" style=""></button>
</div>
<div class="p-4 border-t border-slate-200/60 flex items-center gap-3">
<img alt="User profile" class="w-10 h-10 rounded-full border border-slate-200" data-alt="professional headshot of a person looking forward against a neutral background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBl29XuP3i36CNnVgJIlNE6UZWffZomH4hhezxzki0uGPxCRkWvGhkO9RN0T3E7m26lw12nj7ina0kUg5PcvkcHmNZzeYWgPMiK3Xtc-P6B2jiNBo_8L38tCT7_w0Dv9DoFq-RDNwukHDfjGL-AgWXTG1kKvC7hQqrOlcLloEowbuyBtzc5lGBPJihqF3IscbVt2-6jM5XUr2qxV4SVTMrmMA4zmImV-zEzq0pidrcdINAE13XODxsa6xT4o5FQ_pJTQYqSOx3-S00" style=""/>
<div class="flex-1 min-w-0">
<p class="text-sm font-medium text-on-surface truncate" style="">Admin User</p>
<p class="text-xs text-on-surface-variant truncate" style="">admin@glacier.ai</p>
</div>
<span class="material-symbols-outlined text-slate-500 cursor-pointer hover:text-sky-600 text-sm" style="">settings</span>
</div>
</nav>
<!-- Main Content Area -->
<main class="flex-1 w-full min-w-0 p-6 lg:p-10">
<!-- Top App Bar for Desktop Content Area (Optional complementary to SideNav) -->
<div class="hidden md:flex justify-between items-center mb-10 w-full">
<div>
<h2 class="text-3xl font-headline font-bold text-on-surface tracking-tight" style="">System Overview</h2>
<p class="text-on-surface-variant mt-1 text-sm" style="">Real-time credit consumption metrics</p>
</div>
<div class="flex items-center gap-4">
<div class="relative glass-panel rounded-full px-4 py-2 flex items-center gap-2">
<span class="material-symbols-outlined text-on-surface-variant text-sm" style="">calendar_today</span>
<span class="text-sm text-on-surface" style="">Last 30 Days</span>
<span class="material-symbols-outlined text-on-surface-variant text-sm" style="">expand_more</span>
</div>
<button class="glass-panel p-2 rounded-full hover:bg-slate-100 transition-colors" style="">
<span class="material-symbols-outlined text-on-surface" style="">notifications</span>
</button>
</div>
</div>
<!-- KPI Cards Grid -->
<div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
<!-- Card 1 -->
<div class="glass-panel rounded-2xl p-6 relative overflow-hidden group">
<div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
<span class="material-symbols-outlined text-6xl text-primary" style="">data_usage</span>
</div>
<h3 class="text-sm font-medium text-on-surface-variant mb-1" style="">Total Monthly Credits Consumed</h3>
<div class="flex items-end gap-3 mt-4">
<span class="text-4xl font-bold text-on-surface tracking-tight" style="">1.24M</span>
<span class="text-sm text-tertiary mb-1 flex items-center" style="">
<span class="material-symbols-outlined text-sm mr-1" style="">trending_up</span> 12%
                    </span>
</div>
<p class="text-xs text-on-surface-variant mt-2" style="">vs. previous 30 days</p>
</div>
<!-- Card 2 -->
<div class="glass-panel rounded-2xl p-6 relative overflow-hidden group">
<div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
<span class="material-symbols-outlined text-6xl text-primary" style="">group</span>
</div>
<h3 class="text-sm font-medium text-on-surface-variant mb-1" style="">Active Users</h3>
<div class="flex items-end gap-3 mt-4">
<span class="text-4xl font-bold text-on-surface tracking-tight" style="">8,402</span>
<span class="text-sm text-primary mb-1 flex items-center" style="">
<span class="material-symbols-outlined text-sm mr-1" style="">trending_up</span> 5%
                    </span>
</div>
<p class="text-xs text-on-surface-variant mt-2" style="">unique users this month</p>
</div>
<!-- Card 3 -->
<div class="glass-panel-elevated rounded-2xl p-6 relative overflow-hidden group border-primary/20">
<div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
<span class="material-symbols-outlined text-6xl text-primary" style="">account_balance_wallet</span>
</div>
<div class="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-50"></div>
<h3 class="text-sm font-medium text-primary mb-1 relative z-10" style="">Remaining Budget</h3>
<div class="flex items-end gap-3 mt-4 relative z-10">
<span class="text-4xl font-bold text-on-surface tracking-tight" style="">2.76M</span>
<span class="text-sm text-on-surface-variant mb-1" style="">Credits</span>
</div>
<!-- Progress Bar -->
<div class="mt-4 relative z-10">
<div class="flex justify-between text-xs mb-1 text-on-surface-variant">
<span class="" style="">Usage</span>
<span class="" style="">31%</span>
</div>
<div class="w-full bg-surface-container-high rounded-full h-1.5 overflow-hidden">
<div class="bg-primary h-1.5 rounded-full shadow-[0_0_8px_rgba(14,165,233,0.4)]" style="width: 31%"></div>
</div>
</div>
</div>
</div>
<!-- Bento Grid Layout for Main Content -->
<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
<!-- Large Chart Section (Spans 2 columns) -->
<div class="lg:col-span-2 glass-panel rounded-2xl p-6 flex flex-col h-[400px]">
<div class="flex justify-between items-center mb-6">
<div>
<h3 class="text-lg font-semibold text-on-surface" style="">Credit Consumption Trend</h3>
<p class="text-xs text-on-surface-variant mt-1" style="">Daily usage over last 30 days</p>
</div>
<div class="flex gap-2">
<button class="px-3 py-1 rounded-lg bg-surface-container-high text-xs text-on-surface hover:bg-slate-200 transition-colors border border-outline-variant" style="">Daily</button>
<button class="px-3 py-1 rounded-lg bg-primary/10 text-xs text-primary border border-primary/20 shadow-[0_2px_10px_rgba(14,165,233,0.05)]" style="">Weekly</button>
</div>
</div>
<div class="flex-1 relative w-full h-full">
<!-- Abstract Chart Representation using CSS -->
<div class="chart-container">
<!-- Y-axis labels -->
<div class="absolute left-0 top-0 h-full flex flex-col justify-between text-xs text-on-surface-variant py-4 z-10">
<span class="" style="">100k</span>
<span class="" style="">75k</span>
<span class="" style="">50k</span>
<span class="" style="">25k</span>
<span class="" style="">0</span>
</div>
<!-- Grid Lines -->
<div class="absolute left-8 right-0 top-0 h-full flex flex-col justify-between py-4 z-0">
<div class="border-t border-surface-container-high w-full"></div>
<div class="border-t border-surface-container-high w-full"></div>
<div class="border-t border-surface-container-high w-full"></div>
<div class="border-t border-surface-container-high w-full"></div>
<div class="border-t border-outline-variant w-full"></div>
</div>
<!-- The "Frozen Light" Line Chart -->
<div class="absolute left-8 right-0 bottom-4 top-4 z-10 overflow-hidden">
<svg class="w-full h-full" preserveaspectratio="none" viewbox="0 0 100 100">
<defs>
<lineargradient id="chartGradient" x1="0%" x2="0%" y1="0%" y2="100%">
<stop offset="0%" stop-color="rgba(14, 165, 233, 0.2)"></stop>
<stop offset="100%" stop-color="rgba(14, 165, 233, 0.0)"></stop>
</lineargradient>
<filter id="glow">
<fegaussianblur result="coloredBlur" stddeviation="1"></fegaussianblur>
<femerge>
<femergenode in="coloredBlur"></femergenode>
<femergenode in="SourceGraphic"></femergenode>
</femerge>
</filter>
</defs>
<!-- Fill area -->
<path d="M0,80 Q10,60 20,70 T40,40 T60,50 T80,20 T100,30 L100,100 L0,100 Z" fill="url(#chartGradient)"></path>
<!-- Line -->
<path d="M0,80 Q10,60 20,70 T40,40 T60,50 T80,20 T100,30" fill="none" filter="url(#glow)" stroke="#0ea5e9" stroke-width="1.5"></path>
<!-- Data points -->
<circle cx="40" cy="40" fill="#ffffff" r="1.5" stroke="#0ea5e9" stroke-width="1"></circle>
<circle cx="80" cy="20" fill="#ffffff" r="1.5" stroke="#0ea5e9" stroke-width="1"></circle>
<!-- Highlight point with tooltip line -->
<line opacity="0.3" stroke="#0ea5e9" stroke-dasharray="2,2" stroke-width="0.5" x1="80" x2="80" y1="20" y2="100"></line>
</svg>
</div>
<!-- Tooltip -->
<div class="absolute top-[10%] left-[75%] glass-panel-elevated px-3 py-2 rounded-lg z-20 pointer-events-none">
<p class="text-xs text-on-surface-variant mb-1" style="">Nov 24</p>
<p class="text-sm font-semibold text-primary" style="">82,450 Credits</p>
</div>
<!-- X-axis labels -->
<div class="absolute left-8 right-0 bottom-0 flex justify-between text-xs text-on-surface-variant z-10">
<span class="" style="">Nov 1</span>
<span class="" style="">Nov 8</span>
<span class="" style="">Nov 15</span>
<span class="" style="">Nov 22</span>
<span class="" style="">Nov 30</span>
</div>
</div>
</div>
</div>
<!-- Top Users List Section (Spans 1 column) -->
<div class="glass-panel rounded-2xl p-0 flex flex-col h-[400px] overflow-hidden">
<div class="p-6 border-b border-slate-200/60">
<h3 class="text-lg font-semibold text-on-surface" style="">Top Credit Users</h3>
<p class="text-xs text-on-surface-variant mt-1" style="">Highest consumption this period</p>
</div>
<div class="flex-1 overflow-y-auto px-2 py-2 no-scrollbar">
<ul class="space-y-1">
<!-- User Item 1 -->
<li class="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container-high transition-colors cursor-pointer group" style="">
<div class="flex items-center gap-3">
<div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs border border-primary/20" style="">
                                    AP
                                </div>
<div>
<p class="text-sm font-medium text-on-surface group-hover:text-primary transition-colors" style="">Alex Parker</p>
<p class="text-xs text-on-surface-variant" style="">Data Engineering</p>
</div>
</div>
<div class="text-right">
<p class="text-sm font-semibold text-on-surface" style="">142k</p>
<p class="text-[10px] text-on-surface-variant" style="">Credits</p>
</div>
</li>
<!-- User Item 2 -->
<li class="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container-high transition-colors cursor-pointer group" style="">
<div class="flex items-center gap-3">
<img alt="Sarah J" class="w-8 h-8 rounded-full border border-slate-200" data-alt="professional headshot of a woman looking forward against a neutral background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAtkd4caB2dU6PYleAxefIw9avTG_ZowOYCTC7xB13IguRp5-Lo6vXTwdKDw0EXV8KxjnBDuHsCtasi2UQYDWkr1m9APshJeOTsqhv0oLYOKMBiUH02KjQ82ZTE1USnNol5PxVUg1cfldwCFckU01qB7txpo8e4GCLpyVBXgk1GIyiElCcEhVuecCchBkbvMnnVp_IWacNuHenfVYiDFseGj1XM2Np7bc_WFBq9-pJm9rBO8PkYq0YHkl40IVMqqKd1mLZTIw1RYbw" style=""/>
<div>
<p class="text-sm font-medium text-on-surface group-hover:text-primary transition-colors" style="">Sarah Jenkins</p>
<p class="text-xs text-on-surface-variant" style="">Product AI</p>
</div>
</div>
<div class="text-right">
<p class="text-sm font-semibold text-on-surface" style="">98k</p>
<p class="text-[10px] text-on-surface-variant" style="">Credits</p>
</div>
</li>
<!-- User Item 3 -->
<li class="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container-high transition-colors cursor-pointer group" style="">
<div class="flex items-center gap-3">
<div class="w-8 h-8 rounded-full bg-tertiary/10 flex items-center justify-center text-tertiary font-bold text-xs border border-tertiary/20" style="">
                                    MK
                                </div>
<div>
<p class="text-sm font-medium text-on-surface group-hover:text-primary transition-colors" style="">Marcus Kline</p>
<p class="text-xs text-on-surface-variant" style="">Research</p>
</div>
</div>
<div class="text-right">
<p class="text-sm font-semibold text-on-surface" style="">85k</p>
<p class="text-[10px] text-on-surface-variant" style="">Credits</p>
</div>
</li>
<!-- User Item 4 -->
<li class="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container-high transition-colors cursor-pointer group" style="">
<div class="flex items-center gap-3">
<img alt="David C" class="w-8 h-8 rounded-full border border-slate-200" data-alt="professional headshot of a man looking forward against a neutral background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCGtU8zb99hs3W67VaGsctKcaHvn_9tBLONMkf2T0D91oxTIcX0apCwdV1zCLUa_dx93TMCVt7ttfU3q-EJkiI59EaU-6YxHSDNU5H-XcY6gCL3uOXCLelgFNQytEurmJ2ghYR4oNsp9O618cwF-lnXWqHMunFVSZ32T21AucSZzsmATkW6cTdpAuPPvmn691suNWNf52sdynJSA8zLhznrCo26-13RkNmZbOdDaG2IisVASuHsq8--ZVj4h2U1HATwbV7lACFozPs" style=""/>
<div>
<p class="text-sm font-medium text-on-surface group-hover:text-primary transition-colors" style="">David Chen</p>
<p class="text-xs text-on-surface-variant" style="">Marketing</p>
</div>
</div>
<div class="text-right">
<p class="text-sm font-semibold text-on-surface" style="">62k</p>
<p class="text-[10px] text-on-surface-variant" style="">Credits</p>
</div>
</li>
<!-- User Item 5 -->
<li class="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container-high transition-colors cursor-pointer group" style="">
<div class="flex items-center gap-3">
<div class="w-8 h-8 rounded-full bg-secondary/10 flex items-center justify-center text-secondary font-bold text-xs border border-secondary/20" style="">
                                    EL
                                </div>
<div>
<p class="text-sm font-medium text-on-surface group-hover:text-primary transition-colors" style="">Elena Rostova</p>
<p class="text-xs text-on-surface-variant" style="">Operations</p>
</div>
</div>
<div class="text-right">
<p class="text-sm font-semibold text-on-surface" style="">41k</p>
<p class="text-[10px] text-on-surface-variant" style="">Credits</p>
</div>
</li>
</ul>
</div>
<div class="p-4 border-t border-slate-200/60 text-center">
<button class="text-xs text-primary hover:text-sky-600 transition-colors font-medium" style="">View All Users</button>
</div>
</div>
</div>
</main>
<style>
        /* Hide scrollbar for Chrome, Safari and Opera */
        .no-scrollbar::-webkit-scrollbar {
            display: none;
        }
        /* Hide scrollbar for IE, Edge and Firefox */
        .no-scrollbar {
            -ms-overflow-style: none;  /* IE and Edge */
            scrollbar-width: none;  /* Firefox */
        }
    </style>
</body></html>