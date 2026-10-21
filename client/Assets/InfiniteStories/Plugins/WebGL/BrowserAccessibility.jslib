mergeInto(LibraryManager.library, {
  IS_AccessibleView: function (value) {
    if (window.infiniteStoriesView) window.infiniteStoriesView(UTF8ToString(value));
  },
  IS_AccessibleStatus: function (value) {
    if (window.infiniteStoriesStatus) window.infiniteStoriesStatus(UTF8ToString(value));
  }
});
