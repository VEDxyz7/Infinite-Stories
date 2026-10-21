using UnityEngine;

namespace InfiniteStories
{
    // Small original procedural assets; no external images or Qloo-derived art.
    public static class OriginalArt
    {
        public static Sprite Solid(Color color)
        {
            var texture = new Texture2D(8, 8) { filterMode = FilterMode.Point };
            var pixels = new Color[64]; for (int i = 0; i < pixels.Length; i++) pixels[i] = color;
            texture.SetPixels(pixels); texture.Apply();
            return Sprite.Create(texture, new Rect(0, 0, 8, 8), new Vector2(.5f, .5f), 8);
        }
        public static Sprite Traveler(bool walking)
        {
            var texture = new Texture2D(12, 18) { filterMode = FilterMode.Point };
            var pixels = new Color[216];
            Color coat = new Color(.32f, .55f, .58f), face = new Color(.92f, .74f, .48f), dark = new Color(.07f, .12f, .19f);
            for (int y = 0; y < 18; y++) for (int x = 0; x < 12; x++)
            {
                Color c = Color.clear;
                if (y >= 3 && y < 12 && x >= 3 && x <= 8) c = coat;
                if (y >= 12 && y <= 16 && x >= 4 && x <= 7) c = face;
                if (y == 16 && x >= 3 && x <= 8) c = dark;
                if (y < 3 && (x == (walking ? 3 : 4) || x == 7)) c = dark;
                if (y >= 7 && y <= 9 && x >= 9 && x <= 10) c = new Color(1f, .75f, .3f);
                pixels[y * 12 + x] = c;
            }
            texture.SetPixels(pixels); texture.Apply();
            return Sprite.Create(texture, new Rect(0, 0, 12, 18), new Vector2(.5f, .2f), 12);
        }
    }
}
