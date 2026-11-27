using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace BeadCraftLauncher
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string appScript = Path.Combine(baseDir, "app.py");

            if (!File.Exists(appScript))
            {
                MessageBox.Show(
                    "未找到核心程序文件 app.py，请确保『拼豆工坊.exe』位于项目根目录下运行。",
                    "拼豆工坊启动提示",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
                return;
            }

            string pythonExe = FindPythonExecutable();
            if (string.IsNullOrEmpty(pythonExe))
            {
                MessageBox.Show(
                    "未检测到 Python 3 运行环境，请确认系统已安装 Python 3.10+。",
                    "拼豆工坊环境提示",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return;
            }

            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = pythonExe,
                Arguments = "\"" + appScript + "\"",
                WorkingDirectory = baseDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };

            try
            {
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "启动拼豆工坊失败：\n" + ex.Message,
                    "拼豆工坊启动错误",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        private static string FindPythonExecutable()
        {
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] candidates = new string[]
            {
                Path.Combine(localAppData, @"Programs\Python\Python312\pythonw.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python311\pythonw.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python313\pythonw.exe"),
                "pythonw.exe",
                "python.exe"
            };

            foreach (string candidate in candidates)
            {
                if (Path.IsPathRooted(candidate))
                {
                    if (File.Exists(candidate)) return candidate;
                }
                else
                {
                    string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
                    foreach (string dir in pathEnv.Split(Path.PathSeparator))
                    {
                        if (string.IsNullOrWhiteSpace(dir)) continue;
                        string full = Path.Combine(dir.Trim(), candidate);
                        if (File.Exists(full)) return full;
                    }
                }
            }
            return null;
        }
    }
}
