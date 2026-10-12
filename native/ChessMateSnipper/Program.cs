using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Net;
using System.Threading;
using System.Windows.Forms;

class Program
{
    static readonly string Prefix = "http://127.0.0.1:8765/";

    static HttpListener listener;
    static ScanOverlay overlay;

    static readonly object sync = new object();

    static Bitmap latestBitmap;
    static int scanVersion = 0;

    [STAThread]
    static void Main()
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);

        Console.WriteLine("=== CHESSMATE DIRECT SCREEN SCANNER ===");
        Console.WriteLine("Click Scan -> drag board -> release.");
        Console.WriteLine("No Windows Snipping Tool.");
        Console.WriteLine("No clipboard.");
        Console.WriteLine("Temporary image exists only in RAM.");

        listener = new HttpListener();
        listener.Prefixes.Add(Prefix);
        listener.Start();

        Console.WriteLine("BRIDGE_LISTENING " + Prefix);

        Thread uiThread = new Thread(StartOverlay);
        uiThread.SetApartmentState(ApartmentState.STA);
        uiThread.IsBackground = true;
        uiThread.Start();

        while (true)
        {
            try
            {
                HttpListenerContext context = listener.GetContext();
                HandleRequest(context);
            }
            catch (HttpListenerException)
            {
                break;
            }
            catch (Exception ex)
            {
                Console.WriteLine("HTTP_ERROR " + ex.Message);
            }
        }
    }

    static void StartOverlay()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        overlay = new ScanOverlay();

        Application.Run(overlay);
    }

    static void HandleRequest(HttpListenerContext context)
    {
        context.Response.Headers.Add(
            "Access-Control-Allow-Origin", "*");

        context.Response.Headers.Add(
            "Access-Control-Allow-Methods", "GET, OPTIONS");

        context.Response.Headers.Add(
            "Access-Control-Allow-Headers", "*");

        if (context.Request.HttpMethod == "OPTIONS")
        {
            context.Response.StatusCode = 204;
            context.Response.Close();
            return;
        }

        string path = context.Request.Url.AbsolutePath;

        if (path == "/health")
        {
            WriteText(context, "CHESSMATE_DIRECT_SCANNER_OK");
            return;
        }

        if (path == "/scan")
        {
            StartScan();

            WriteText(context, "SCAN_STARTED");
            return;
        }

        if (path == "/version")
        {
            int version;

            lock (sync)
            {
                version = scanVersion;
            }

            WriteText(context, version.ToString());
            return;
        }

        if (path == "/image")
        {
            SendLatestImage(context);
            return;
        }

        context.Response.StatusCode = 404;
        WriteText(context, "NOT_FOUND");
    }

    static void StartScan()
    {
        if (overlay == null)
            return;

        try
        {
            overlay.BeginInvoke(new Action(() =>
            {
                overlay.StartSelection();
            }));
        }
        catch (Exception ex)
        {
            Console.WriteLine("SCAN_START_ERROR " + ex.Message);
        }
    }

    static void CaptureFinished(Rectangle screenRectangle)
    {
        try
        {
            using Bitmap captured = new Bitmap(
                screenRectangle.Width,
                screenRectangle.Height,
                PixelFormat.Format32bppArgb);

            using Graphics graphics =
                Graphics.FromImage(captured);

            graphics.CopyFromScreen(
                screenRectangle.Location,
                Point.Empty,
                screenRectangle.Size);

            Bitmap newBitmap = new Bitmap(captured);

            lock (sync)
            {
                latestBitmap?.Dispose();
                latestBitmap = newBitmap;
                scanVersion++;
            }

            Console.WriteLine(
                "SCAN_CAPTURED " +
                screenRectangle.Width +
                "x" +
                screenRectangle.Height +
                " VERSION=" +
                scanVersion);
        }
        catch (Exception ex)
        {
            Console.WriteLine(
                "CAPTURE_ERROR " + ex.Message);
        }
    }

    static void SendLatestImage(HttpListenerContext context)
    {
        Bitmap bitmap = null;

        try
        {
            lock (sync)
            {
                if (latestBitmap != null)
                    bitmap = new Bitmap(latestBitmap);
            }

            if (bitmap == null)
            {
                context.Response.StatusCode = 404;
                WriteText(context, "NO_IMAGE");
                return;
            }

            using (bitmap)
            using (MemoryStream stream = new MemoryStream())
            {
                bitmap.Save(stream, ImageFormat.Png);

                byte[] data = stream.ToArray();

                context.Response.ContentType = "image/png";
                context.Response.ContentLength64 = data.Length;

                context.Response.OutputStream.Write(
                    data,
                    0,
                    data.Length);

                context.Response.Close();
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine(
                "IMAGE_ERROR " + ex.Message);

            try
            {
                context.Response.StatusCode = 500;
                WriteText(context, "IMAGE_ERROR");
            }
            catch
            {
            }
        }
    }

    static void WriteText(
        HttpListenerContext context,
        string text)
    {
        byte[] data =
            System.Text.Encoding.UTF8.GetBytes(text);

        context.Response.ContentType =
            "text/plain";

        context.Response.ContentLength64 =
            data.Length;

        context.Response.OutputStream.Write(
            data,
            0,
            data.Length);

        context.Response.Close();
    }

    class ScanOverlay : Form
    {
        bool selecting;

        Point startPoint;
        Point currentPoint;

        Rectangle virtualScreen;

        public ScanOverlay()
        {
            FormBorderStyle =
                FormBorderStyle.None;

            ShowInTaskbar = false;

            TopMost = true;

            BackColor = Color.Black;

            Opacity = 0.30;

            DoubleBuffered = true;

            Cursor = Cursors.Cross;

            KeyPreview = true;

            virtualScreen =
                SystemInformation.VirtualScreen;

            StartPosition =
                FormStartPosition.Manual;

            Location =
                virtualScreen.Location;

            Size =
                virtualScreen.Size;

            Hide();
        }

        public void StartSelection()
        {
            virtualScreen =
                SystemInformation.VirtualScreen;

            Location =
                virtualScreen.Location;

            Size =
                virtualScreen.Size;

            selecting = false;

            Show();

            Activate();

            Focus();
        }

        protected override void OnMouseDown(
            MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left)
                return;

            selecting = true;

            startPoint = e.Location;

            currentPoint = e.Location;

            Invalidate();
        }

        protected override void OnMouseMove(
            MouseEventArgs e)
        {
            if (!selecting)
                return;

            currentPoint = e.Location;

            Invalidate();
        }

        protected override void OnMouseUp(
            MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left)
                return;

            if (!selecting)
                return;

            selecting = false;

            currentPoint = e.Location;

            Rectangle rectangle =
                GetSelectionRectangle();

            Hide();

            if (rectangle.Width < 50 ||
                rectangle.Height < 50)
            {
                return;
            }

            Rectangle screenRectangle =
                new Rectangle(
                    rectangle.X + virtualScreen.X,
                    rectangle.Y + virtualScreen.Y,
                    rectangle.Width,
                    rectangle.Height);

            CaptureFinished(screenRectangle);
        }

        protected override void OnKeyDown(
            KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Escape)
            {
                selecting = false;
                Hide();
            }
        }

        Rectangle GetSelectionRectangle()
        {
            int x = Math.Min(
                startPoint.X,
                currentPoint.X);

            int y = Math.Min(
                startPoint.Y,
                currentPoint.Y);

            int right = Math.Max(
                startPoint.X,
                currentPoint.X);

            int bottom = Math.Max(
                startPoint.Y,
                currentPoint.Y);

            return new Rectangle(
                x,
                y,
                right - x,
                bottom - y);
        }

        protected override void OnPaint(
            PaintEventArgs e)
        {
            base.OnPaint(e);

            if (!selecting)
                return;

            Rectangle rectangle =
                GetSelectionRectangle();

            using Pen pen =
                new Pen(Color.White, 2);

            e.Graphics.DrawRectangle(
                pen,
                rectangle);
        }
    }
}
