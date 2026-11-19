/** Take a photo in the installed app, or open the camera input in the browser. */

type CameraPhoto = { base64String?: string; format?: string };

type NativeCamera = {
  getPhoto: (options: {
    quality: number;
    allowEditing: boolean;
    resultType: string;
    source: string;
    correctOrientation: boolean;
  }) => Promise<CameraPhoto>;
};

function nativeCamera(): NativeCamera | null {
  if (typeof window === "undefined") return null;
  const cap = (window as Window & {
    Capacitor?: { isNativePlatform?: () => boolean; Plugins?: { Camera?: NativeCamera } };
  }).Capacitor;
  if (!cap?.isNativePlatform?.() || !cap.Plugins?.Camera) return null;
  return cap.Plugins.Camera;
}

export async function takePhoto(): Promise<File | null> {
  const camera = nativeCamera();
  if (!camera) return null;
  const photo = await camera.getPhoto({
    quality: 70,
    allowEditing: false,
    resultType: "base64",
    source: "CAMERA",
    correctOrientation: true,
  });
  if (!photo.base64String) return null;
  const bytes = Uint8Array.from(atob(photo.base64String), (char) => char.charCodeAt(0));
  const format = photo.format === "png" ? "png" : "jpeg";
  return new File([bytes], `photo.${format}`, { type: format === "png" ? "image/png" : "image/jpeg" });
}
