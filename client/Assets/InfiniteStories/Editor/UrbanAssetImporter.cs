using UnityEditor;
using UnityEngine;

namespace InfiniteStories.Editor
{
    // Point sampling and no mipmaps preserve the source pack's 16px grid in WebGL.
    public sealed class UrbanAssetImporter : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            if (!assetPath.Contains("/Resources/Art/Urban/")) return;
            var t=(TextureImporter)assetImporter;
            t.textureType=TextureImporterType.Sprite; t.spriteImportMode=SpriteImportMode.Single;
            t.filterMode=FilterMode.Point; t.mipmapEnabled=false; t.alphaIsTransparency=true;
            t.textureCompression=TextureImporterCompression.Uncompressed; t.npotScale=TextureImporterNPOTScale.None;
            t.spritePixelsPerUnit=16;
            int id; string name=System.IO.Path.GetFileNameWithoutExtension(assetPath);
            if(int.TryParse(name.Substring(5),out id) && NightArt.IsCharacter(id)) {
                t.spritePixelsPerUnit=12;
                var settings=new TextureImporterSettings(); t.ReadTextureSettings(settings);
                settings.spriteAlignment=(int)SpriteAlignment.Custom; settings.spritePivot=new Vector2(.5f,.12f); t.SetTextureSettings(settings);
            }
        }
    }
}
