# Lists After Effects' visible top-level windows. -Close "<title>" closes dialogs with that title;
# -Close auto closes the ones that block scripts (font resolver from the phone mockup, untitled alerts).
param([string]$Close = "")
if (-not ('AeWin' -as [type])) { Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public class AeWin { public delegate bool P(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool EnumWindows(P p, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
[DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
public static List<string> For(uint pid, string close){ var r=new List<string>(); EnumWindows((h,l)=>{ uint p; GetWindowThreadProcessId(h,out p); if(p==pid && IsWindowVisible(h)){ var s=new StringBuilder(300); GetWindowText(h,s,300); var c=new StringBuilder(200); GetClassName(h,c,200); r.Add("["+c+"] '"+s+"' enabled="+IsWindowEnabled(h)); if(c.ToString()=="#32770" && ((close=="auto" && (s.ToString()=="Solucionar fontes" || s.ToString()=="Resolve Fonts" || s.Length==0)) || (close!="" && close!="auto" && s.ToString()==close))){ PostMessage(h,0x0010,IntPtr.Zero,IntPtr.Zero); r.Add("  -> closed"); } } return true; }, IntPtr.Zero); return r; } }
"@
}
$ps = Get-Process AfterFX -ErrorAction SilentlyContinue
if (-not $ps) { "After Effects is not running" }
foreach ($p in $ps) { "PID $($p.Id) started $($p.StartTime) responding=$($p.Responding)"; [AeWin]::For([uint32]$p.Id, $Close) }
