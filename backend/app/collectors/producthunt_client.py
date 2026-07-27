PRODUCT_HUNT_POSTS_QUERY = """
query GetLatestPosts($first: Int!) {
  posts(order: NEWEST, first: $first) {
    edges {
      node {
        id
        name
        tagline
        slug
        url
        website
        createdAt
        topics {
          edges {
            node {
              name
            }
          }
        }
      }
    }
  }
}
"""
