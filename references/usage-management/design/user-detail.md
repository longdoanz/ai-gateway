<!DOCTYPE html>

<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>User Profile &amp; API Tokens</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f8fafc; /* bg-background */
            background-image: 
                radial-gradient(at 0% 0%, hsla(210, 100%, 95%, 1) 0px, transparent 50%),
                radial-gradient(at 100% 0%, hsla(190, 100%, 95%, 1) 0px, transparent 50%),
                radial-gradient(at 100% 100%, hsla(230, 100%, 95%, 1) 0px, transparent 50%),
                radial-gradient(at 0% 100%, hsla(200, 100%, 95%, 1) 0px, transparent 50%);
            background-attachment: fixed;
        }
        .material-symbols-outlined {
            font-variation-settings: 'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24;
        }
        .glass-panel {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.8);
            box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.05);
        }
        .glass-panel-elevated {
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1px solid rgba(255, 255, 255, 0.9);
            box-shadow: 0 16px 40px 0 rgba(31, 38, 135, 0.08);
        }
    </style>
<script id="tailwind-config">tailwind.config = {darkMode: "class", theme: {extend: {colors: {outline: "#777587", "surface-tint": "#4d44e3", "secondary-container": "#dae2fd", "on-secondary-fixed": "#131b2e", "tertiary-fixed-dim": "#ffb695", "surface-container": "#f0ecf9", "surface-container-low": "#f5f2ff", "on-primary-container": "#dad7ff", "inverse-primary": "#c3c0ff", "surface-variant": "#e4e1ee", "secondary-fixed": "#dae2fd", secondary: "#565e74", "on-tertiary": "#ffffff", "surface-container-lowest": "#ffffff", "outline-variant": "#c7c4d8", background: "#fcf8ff", "on-error-container": "#93000a", "primary-fixed": "#e2dfff", "surface-bright": "#fcf8ff", "on-surface": "#1b1b24", "on-error": "#ffffff", tertiary: "#7e3000", "on-secondary": "#ffffff", "on-primary-fixed": "#0f0069", "on-secondary-fixed-variant": "#3f465c", "on-primary-fixed-variant": "#3323cc", "on-secondary-container": "#5c647a", error: "#ba1a1a", "surface-container-high": "#eae6f4", "surface-container-highest": "#e4e1ee", "on-surface-variant": "#464555", "inverse-on-surface": "#f3effc", "primary-fixed-dim": "#c3c0ff", "on-tertiary-fixed": "#351000", "tertiary-fixed": "#ffdbcc", "tertiary-container": "#a44100", "primary-container": "#4f46e5", "inverse-surface": "#302f39", "on-background": "#1b1b24", "on-primary": "#ffffff", primary: "#3525cd", "on-tertiary-container": "#ffd2be", "surface-dim": "#dcd8e5", surface: "#fcf8ff", "secondary-fixed-dim": "#bec6e0", "error-container": "#ffdad6", "on-tertiary-fixed-variant": "#7b2f00"}, borderRadius: {DEFAULT: "0.25rem", lg: "0.5rem", xl: "0.75rem", full: "9999px"}, fontFamily: {headline: ["Inter"], display: ["Inter"], body: ["Inter"], label: ["Inter"], "body-base": ["Inter"], "mono-label": ["Inter"], h2: ["Inter"], h1: ["Inter"], "body-sm": ["Inter"], "label-caps": ["Inter"]}, fontSize: {"body-base": ["14px", {lineHeight: "1.5", letterSpacing: "0", fontWeight: "400"}], "mono-label": ["12px", {lineHeight: "1", letterSpacing: "-0.01em", fontWeight: "500"}], h2: ["24px", {lineHeight: "1.3", letterSpacing: "-0.01em", fontWeight: "600"}], display: ["48px", {lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "600"}], h1: ["30px", {lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600"}], "body-sm": ["13px", {lineHeight: "1.5", letterSpacing: "0", fontWeight: "400"}], "label-caps": ["11px", {lineHeight: "1", letterSpacing: "0.05em", fontWeight: "600"}]}, spacing: {"bento-gap": "16px", "container-padding": "24px", margin: "32px", gutter: "24px", unit: "4px"}}}};</script>
</head>
<body class="bg-background text-on-surface font-body antialiased min-h-screen flex">
<!-- SideNavBar -->
<nav class="hidden md:flex h-screen w-64 border-r border-white/60 bg-white/40 backdrop-blur-2xl shadow-[4px_0_24px_rgba(0,0,0,0.02)] fixed left-0 top-0 h-full z-40 flex-col font-inter">
<div class="p-6 flex flex-col h-full">
<div class="mb-8">
<h1 class="text-xl font-bold tracking-tight text-primary">Glacier AI</h1>
<p class="text-sm text-on-surface-variant mt-1 font-medium">Credit Manager</p>
</div>
<div class="flex-1 space-y-2">
<a class="flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-white/60 hover:text-primary transition-colors active:scale-95 duration-200 rounded-xl font-medium" href="#">
<span class="material-symbols-outlined" data-icon="dashboard">dashboard</span>
<span>Dashboard</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-white/60 hover:text-primary transition-colors active:scale-95 duration-200 rounded-xl font-medium" href="#">
<span class="material-symbols-outlined" data-icon="group">group</span>
<span>Directory</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-primary bg-white/80 shadow-sm border border-white rounded-xl active:scale-95 duration-200 font-medium" href="#">
<span class="material-symbols-outlined" data-icon="person">person</span>
<span>Profile</span>
</a>
<a class="flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-white/60 hover:text-primary transition-colors active:scale-95 duration-200 rounded-xl font-medium" href="#">
<span class="material-symbols-outlined" data-icon="analytics">analytics</span>
<span>Analytics</span>
</a>
</div>
<div class="mt-auto">
</div>
</div>
</nav>
<!-- Main Content Wrapper -->
<div class="flex-1 md:ml-64 flex flex-col min-h-screen">
<!-- TopNavBar Wrapper for Mobile -->
<header class="md:hidden sticky top-0 w-full z-30 flex justify-between items-center px-6 h-16 border-b border-white/60 bg-white/40 backdrop-blur-2xl shadow-[0_4px_24px_rgba(0,0,0,0.02)] font-inter">
<h1 class="text-xl font-bold tracking-tight text-primary">Glacier AI</h1>
<div class="flex items-center gap-4">
<button class="text-on-surface-variant hover:text-primary transition-opacity cursor-pointer">
<span class="material-symbols-outlined" data-icon="notifications">notifications</span>
</button>
<img alt="User avatar" class="w-8 h-8 rounded-full border border-white object-cover shadow-sm" data-alt="close up portrait of a young woman with natural makeup looking directly at camera, soft lighting" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAKIQpctpzQwEP-1EMX0BNEmMaRfrPIlR-nm0myXX2JcyXU4l1Vzs2ovQtH4gf9tAvfzGjng1048w-0FecOo4CWgcOXDXGRHkpDQffSG4HD1wt365HHtSD7ukratJluxg3ETxM4SB6trnCId9qLXSIgXCnI0USNkn_Q0UT5ltpVwCey5xhDXX-Dj6p_anmeCAxLogWgsTJrPQkEnDrhWbX9lu6O_FJbDSSZStejxCz9UQsbLUu5XBq6MoPTh8gokic1d3c0Nw7x08s"/>
</div>
</header>
<!-- Main Content -->
<main class="flex-1 p-6 md:p-10 lg:p-12 max-w-7xl mx-auto w-full">
<div class="mb-10">
<h2 class="text-3xl font-bold font-headline text-on-surface tracking-tight">Profile &amp; Security</h2>
<p class="text-on-surface-variant mt-2 font-body text-lg">Manage your personal information and API credentials.</p>
</div>
<div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
<!-- Left Pane: User Info & Actions -->
<div class="lg:col-span-4 space-y-6">
<!-- User Card -->
<div class="glass-panel rounded-3xl p-8 relative overflow-hidden group">
<div class="absolute inset-0 bg-gradient-to-br from-white/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
<div class="flex flex-col items-center text-center relative z-10">
<div class="relative mb-6">
<img alt="User profile" class="w-28 h-28 rounded-full border-4 border-white object-cover shadow-lg" data-alt="close up portrait of a young woman with natural makeup looking directly at camera, soft lighting" src="https://lh3.googleusercontent.com/aida-public/AB6AXuANa75jFjhmFPQnpmerpO5A1oJPUULcVeRDT7Ggihk65AHIL0BH_oOqUxN4Xy7wCitM7NX8wSowho_752rW4sGNYXTA5BLy9Q_8QG6DFfLd1ATtOSOlBexB8Ibu4YoU-h9VmQSJMDryw9x_2H6J-74HtWopugNKOBnq1nuYsCaMqZACRZuaAkNgEQWhetsXfIIpznF-KAAsNasb7Vds7qEt9AR63OfUZg5CHRGkU8Rog_sSa79SQ-KZk6zmJ1kgRh4BpVzEwo7wDRs"/>
<button class="absolute bottom-1 right-1 bg-white border border-outline-variant/30 p-2 rounded-full text-on-surface-variant hover:text-primary transition-colors shadow-sm">
<span class="material-symbols-outlined text-sm" data-icon="edit">edit</span>
</button>
</div>
<h3 class="text-2xl font-bold text-on-surface font-headline tracking-tight">Elena Rostova</h3>
<p class="text-on-surface-variant text-sm mt-1.5 font-medium">elena.rostova@example.com</p>
<div class="mt-5 inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white border border-outline-variant/20 text-primary text-xs font-semibold shadow-sm">
<span class="w-2 h-2 rounded-full bg-primary shadow-[0_0_8px_rgba(2,132,199,0.4)]"></span>
                                Pro Plan
                            </div>
</div>
<div class="mt-8 space-y-4 relative z-10 border-t border-outline-variant/30 pt-6">
<div class="flex justify-between items-center text-sm">
<span class="text-on-surface-variant font-medium">Member Since</span>
<span class="text-on-surface font-semibold">Oct 2023</span>
</div>
<div class="flex justify-between items-center text-sm">
<span class="text-on-surface-variant font-medium">Region</span>
<span class="text-on-surface font-semibold">EU-West-1</span>
</div>
</div>
</div>
<!-- Account Actions -->
<div class="glass-panel rounded-3xl p-6">
<h4 class="text-xs font-bold text-on-surface-variant uppercase tracking-widest mb-5 ml-2">Account Actions</h4>
<div class="space-y-3">
<button class="w-full flex items-center justify-between px-5 py-4 rounded-2xl bg-white/50 border border-white hover:bg-white hover:shadow-sm transition-all text-sm font-semibold text-on-surface group">
<span class="flex items-center gap-3">
<span class="material-symbols-outlined text-on-surface-variant group-hover:text-primary transition-colors" data-icon="lock_reset">lock_reset</span>
                                    Change Password
                                </span>
<span class="material-symbols-outlined text-on-surface-variant text-sm" data-icon="chevron_right">chevron_right</span>
</button>
<button class="w-full flex items-center justify-between px-5 py-4 rounded-2xl bg-error/5 border border-error/10 hover:bg-error/10 transition-all text-sm font-semibold text-error group">
<span class="flex items-center gap-3">
<span class="material-symbols-outlined" data-icon="person_off">person_off</span>
                                    Deactivate Account
                                </span>
</button>
</div>
</div>
</div>
<!-- Right Pane: API & Usage -->
<div class="lg:col-span-8 space-y-6">
<!-- Credits Usage Bento -->
<div class="glass-panel-elevated rounded-3xl p-8 md:p-10">
<div class="flex flex-col md:flex-row md:items-center justify-between mb-10 gap-4">
<div>
<h3 class="text-2xl font-bold text-on-surface flex items-center gap-3">
<span class="material-symbols-outlined text-primary" data-icon="bolt">bolt</span>
                                    Credits Consumed
                                </h3>
<p class="text-on-surface-variant text-sm mt-2 font-medium">Usage overview for the current billing cycle.</p>
</div>
<div class="text-left md:text-right">
<div class="text-4xl font-display font-bold text-on-surface tracking-tight">45,280</div>
<div class="text-sm text-on-surface-variant font-medium mt-1">/ 100,000 Credits</div>
</div>
</div>
<!-- Simple Bar Chart -->
<div class="h-56 flex items-end justify-between gap-3 mt-6">
<!-- Bars -->
<div class="w-full flex flex-col justify-end group">
<div class="w-full bg-surface-variant/50 rounded-t-lg h-[30%] group-hover:bg-primary/20 transition-colors relative border border-white/50">
<div class="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-xs px-3 py-1.5 rounded-lg shadow-sm border border-outline-variant/20 text-on-surface whitespace-nowrap font-medium z-10">Mon: 12k</div>
</div>
<div class="text-xs text-center mt-3 text-on-surface-variant font-medium">M</div>
</div>
<div class="w-full flex flex-col justify-end group">
<div class="w-full bg-surface-variant/50 rounded-t-lg h-[45%] group-hover:bg-primary/20 transition-colors relative border border-white/50">
<div class="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-xs px-3 py-1.5 rounded-lg shadow-sm border border-outline-variant/20 text-on-surface whitespace-nowrap font-medium z-10">Tue: 18k</div>
</div>
<div class="text-xs text-center mt-3 text-on-surface-variant font-medium">T</div>
</div>
<div class="w-full flex flex-col justify-end group">
<div class="w-full bg-primary/20 border border-primary/30 rounded-t-lg h-[85%] group-hover:bg-primary/30 transition-colors relative shadow-[0_-4px_12px_rgba(2,132,199,0.1)]">
<div class="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-xs px-3 py-1.5 rounded-lg shadow-sm border border-outline-variant/20 text-on-surface whitespace-nowrap font-medium z-20">Wed: 35k</div>
</div>
<div class="text-xs text-center mt-3 text-primary font-bold">W</div>
</div>
<div class="w-full flex flex-col justify-end group">
<div class="w-full bg-surface-variant/50 rounded-t-lg h-[60%] group-hover:bg-primary/20 transition-colors relative border border-white/50">
<div class="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-xs px-3 py-1.5 rounded-lg shadow-sm border border-outline-variant/20 text-on-surface whitespace-nowrap font-medium z-10">Thu: 24k</div>
</div>
<div class="text-xs text-center mt-3 text-on-surface-variant font-medium">T</div>
</div>
<div class="w-full flex flex-col justify-end group">
<div class="w-full bg-surface-variant/50 rounded-t-lg h-[20%] group-hover:bg-primary/20 transition-colors relative border border-white/50">
<div class="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-xs px-3 py-1.5 rounded-lg shadow-sm border border-outline-variant/20 text-on-surface whitespace-nowrap font-medium z-10">Fri: 8k</div>
</div>
<div class="text-xs text-center mt-3 text-on-surface-variant font-medium">F</div>
</div>
<div class="w-full flex flex-col justify-end group">
<div class="w-full bg-surface-variant/50 rounded-t-lg h-[10%] group-hover:bg-primary/20 transition-colors relative border border-white/50">
<div class="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-xs px-3 py-1.5 rounded-lg shadow-sm border border-outline-variant/20 text-on-surface whitespace-nowrap font-medium z-10">Sat: 4k</div>
</div>
<div class="text-xs text-center mt-3 text-on-surface-variant font-medium">S</div>
</div>
<div class="w-full flex flex-col justify-end group">
<div class="w-full bg-surface-variant/50 rounded-t-lg h-[15%] group-hover:bg-primary/20 transition-colors relative border border-white/50">
<div class="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white text-xs px-3 py-1.5 rounded-lg shadow-sm border border-outline-variant/20 text-on-surface whitespace-nowrap font-medium z-10">Sun: 6k</div>
</div>
<div class="text-xs text-center mt-3 text-on-surface-variant font-medium">S</div>
</div>
</div>
</div>
</div>
</div>
</main>
</div>
</body></html>